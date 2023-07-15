# Copyright 2023 MOSEC Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Managers to control Coordinator and Mosec process."""

import multiprocessing as mp
import subprocess
from functools import partial
from multiprocessing.context import ForkContext, SpawnContext
from multiprocessing.process import BaseProcess
from multiprocessing.synchronize import Event
from pathlib import Path
from time import monotonic, sleep
from typing import Callable, Dict, Iterable, List, Optional, Type, Union, cast

import pkg_resources

from mosec.coordinator import STAGE_EGRESS, STAGE_INGRESS, Coordinator
from mosec.env import env_var_context, validate_env, validate_int_ge
from mosec.ipc import IPCWrapper
from mosec.log import get_internal_logger
from mosec.worker import Worker

logger = get_internal_logger()

NEW_PROCESS_METHOD = {"spawn", "fork"}


# pylint: disable=too-many-instance-attributes
# pylint: disable=too-many-arguments
class Runtime:
    """The wrapper with one worker and its arguments."""

    def __init__(
        self,
        worker: Type[Worker],
        num: int,
        max_batch_size: int,
        max_wait_time: int,
        stage_id: int,
        timeout: int,
        start_method: str,
        env: Union[None, List[Dict[str, str]]],
        ipc_wrapper: Optional[Union[Type[IPCWrapper], partial]],
    ):
        """Initialize the mosec coordinator.

        Args:
            worker (Worker): subclass of `mosec.Worker` implemented by users.
            num (int): number of workers
            max_batch_size: the maximum batch size allowed (>=1), will enable the
                dynamic batching if it > 1
            max_wait_time (int): the maximum wait time (millisecond)
                for dynamic batching, needs to be used with `max_batch_size`
                to enable the feature. If not configure, will use the CLI
                argument `--wait` (default=10ms)
            stage_id (int): identification number for worker stages.
            timeout (int): timeout for the `forward` function.
            start_method: the process starting method ("spawn" or "fork")
            env: the environment variables to set before starting the process
            ipc_wrapper (IPCWrapper): IPC wrapper class to be initialized.

        Raises:
            TypeError: ipc_wrapper should inherit from `IPCWrapper`
        """
        self.worker = worker
        self.num = num
        self.max_batch_size = max_batch_size
        self.max_wait_time = max_wait_time
        self.stage_id = stage_id
        self.timeout = timeout
        self.start_method = start_method
        self.env = env
        self.ipc_wrapper = ipc_wrapper

        # adding the stage id in case the worker class is added to multiple stages
        self.name = f"{self.worker.__name__}_{self.stage_id}"
        self.pool: List[Union[BaseProcess, None]] = [None for _ in range(self.num)]

    @staticmethod
    def process_healthy(process: Union[BaseProcess, None]) -> bool:
        """Check if the child process is healthy.

        ref: https://docs.python.org/3/library/multiprocessing.html

            The exit code will be None if the process has not yet terminated.
        """
        return process is not None and process.exitcode is None

    def healthy(self, method: Callable[[Iterable[object]], bool]) -> bool:
        """Check if all/any of the child processes are healthy."""
        return method(self.pool)

    def start_process(
        self,
        worker_id: int,
        stage_label: str,
        work_path: str,
        shutdown: Event,
        shutdown_notify: Event,
    ):
        """Start a worker process in the context."""
        context = mp.get_context(self.start_method)
        context = cast(Union[SpawnContext, ForkContext], context)
        coordinator_process = context.Process(
            target=Coordinator,
            args=(
                self.worker,
                self.max_batch_size,
                stage_label,
                shutdown,
                shutdown_notify,
                work_path,
                self.stage_id,
                worker_id + 1,
                self.ipc_wrapper,
                self.timeout,
            ),
            daemon=True,
        )

        with env_var_context(self.env, worker_id):
            coordinator_process.start()

        self.pool[worker_id] = coordinator_process

    def check(
        self,
        first: bool,
        stage_label: str,
        work_path: str,
        shutdown: Event,
        shutdown_notify: Event,
    ) -> bool:
        """Check and start the worker process if it has not started yet.

        Args:
            first: whether the worker is tried to start at first time
            stage_label: label of worker ingress and egress
            work_path: path of working directory
            shutdown: Event of server shutdown
            shutdown_notify: Event of server will shutdown

        Returns:
            Whether the worker is started successfully
        """
        # for every sequential stage
        self.pool = [p if self.process_healthy(p) else None for p in self.pool]
        if self.healthy(all):
            # this stage is healthy
            return True
        if not first and not self.healthy(any):
            # this stage might contain bugs
            return False

        need_start_id = [
            worker_id for worker_id in range(self.num) if self.pool[worker_id] is None
        ]
        for worker_id in need_start_id:
            # for every worker in each stage
            self.start_process(
                worker_id, stage_label, work_path, shutdown, shutdown_notify
            )
        return True

    def validate(self):
        """Validate arguments of worker runtime."""
        validate_env(self.env, self.num)
        assert issubclass(
            self.worker, Worker
        ), "worker must be inherited from mosec.Worker"
        validate_int_ge(self.num, "worker number")
        validate_int_ge(self.max_batch_size, "maximum batch size")
        validate_int_ge(self.max_wait_time, "maximum wait time", 0)
        validate_int_ge(self.timeout, "forward timeout", 0)
        assert (
            self.start_method in NEW_PROCESS_METHOD
        ), f"start method must be one of {NEW_PROCESS_METHOD}"


class PyRuntimeManager:
    """The manager to control coordinator process."""

    def __init__(self, work_path: str, shutdown: Event, shutdown_notify: Event):
        """Initialize a coordinator manager.

        Args:
            work_path: path of working directory
            shutdown: Event of server shutdown
            shutdown_notify: Event of server will shutdown
        """
        self.runtimes: List[Runtime] = []

        self._work_path = work_path
        self.shutdown = shutdown
        self.shutdown_notify = shutdown_notify

    def __iter__(self):
        """Iterate workers of manager."""
        return self.runtimes.__iter__()

    @property
    def worker_count(self) -> int:
        """Get number of workers."""
        return len(self.runtimes)

    @property
    def workers(self) -> List[Type[Worker]]:
        """Get List of workers."""
        return [r.worker for r in self.runtimes]

    def egress_mime(self) -> str:
        """Return mime of egress worker."""
        return self.runtimes[-1].worker.resp_mime_type

    def append(self, runtime: Runtime):
        """Sequentially appends workers to the workflow pipeline."""
        self.runtimes.append(runtime)

    def label_stage(self, stage_id: int) -> str:
        """Get the label of the stage (ingress/egress or not)."""
        stage = ""
        if stage_id == 0:
            stage += STAGE_INGRESS
        if stage_id == self.worker_count - 1:
            stage += STAGE_EGRESS
        return stage

    def check_and_start(self, first: bool) -> Union[Runtime, None]:
        """Check all worker processes and try to start failed ones.

        Args:
            first: whether the worker is tried to start at first time
        """
        for stage_id, worker_runtime in enumerate(self.runtimes):
            label = self.label_stage(stage_id)
            success = worker_runtime.check(
                first, label, self._work_path, self.shutdown, self.shutdown_notify
            )
            if not success:
                return worker_runtime
        return None


class RsRuntimeManager:
    """The manager to control Mosec process."""

    def __init__(self, timeout: int):
        """Initialize a Mosec manager.

        Args:
            timeout: service timeout in milliseconds
        """
        self.process: Optional[subprocess.Popen] = None

        self.server_path = Path(
            pkg_resources.resource_filename("mosec", "bin"), "mosec"
        )
        self.timeout = timeout

    def halt(self):
        """Graceful shutdown."""
        # terminate controller first and wait for a graceful period
        if self.process is None:
            return
        self.process.terminate()
        graceful_period = monotonic() + self.timeout / 1000
        while monotonic() < graceful_period:
            ctr_exitcode = self.process.poll()
            if ctr_exitcode is None:
                sleep(0.1)
                continue
            # exited
            if ctr_exitcode:  # on error
                logger.error("mosec service halted on error [%d]", ctr_exitcode)
            else:
                logger.info("mosec service halted normally [%d]", ctr_exitcode)
            break

        if monotonic() > graceful_period:
            logger.error("failed to terminate mosec service, will try to kill it")
            self.process.kill()

    def start(self, config_path: Path) -> subprocess.Popen:
        """Start the Mosec process.

        Args:
            config_path: configuration path of mosec
        """
        # pylint: disable=consider-using-with
        self.process = subprocess.Popen([self.server_path, config_path])
        return self.process
