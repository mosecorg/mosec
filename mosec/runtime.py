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
import sys
from multiprocessing.context import ForkContext, SpawnContext
from multiprocessing.process import BaseProcess
from multiprocessing.synchronize import Event
from pathlib import Path
from time import monotonic, sleep
from typing import Callable, Dict, Iterable, List, Optional, Type, Union, cast

if sys.version_info >= (3, 9):
    from importlib.resources import files as importlib_files
else:
    from pkg_resources import resource_filename

    def importlib_files(package: str) -> Path:
        """Get the resource file path."""
        return Path(resource_filename(package, ""))


from mosec.coordinator import Coordinator
from mosec.env import env_var_context, validate_env, validate_int_ge
from mosec.log import get_internal_logger
from mosec.worker import Worker

logger = get_internal_logger()

NEW_PROCESS_METHOD = {"spawn", "fork"}


# pylint: disable=too-many-instance-attributes
# pylint: disable=too-many-arguments
# pylint: disable=too-few-public-methods
class Runtime:
    """The wrapper with one worker and its arguments."""

    # count how many runtime instances have been created
    _stage_id: int = 0

    def __init__(
        self,
        worker: Type[Worker],
        num: int = 1,
        max_batch_size: int = 1,
        max_wait_time: int = 10,
        timeout: int = 3,
        start_method: str = "spawn",
        env: Union[None, List[Dict[str, str]]] = None,
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
            timeout (int): timeout (second) for the `forward` function.
            start_method: the process starting method ("spawn" or "fork")
            env: the environment variables to set before starting the process

        """
        self.worker = worker
        self.num = num
        self.max_batch_size = max_batch_size
        self.max_wait_time = max_wait_time
        self.timeout = timeout
        self.start_method = start_method
        self.env = env

        Runtime._stage_id += 1
        # adding the stage id in case the worker class is added to multiple stages
        self.name = f"{self.worker.__name__}_{self._stage_id}"
        self._pool: List[Union[BaseProcess, None]] = [None for _ in range(self.num)]

        self._validate()

    @staticmethod
    def _process_healthy(process: Union[BaseProcess, None]) -> bool:
        """Check if the child process is healthy.

        ref: https://docs.python.org/3/library/multiprocessing.html

            The exit code will be None if the process has not yet terminated.
        """
        return process is not None and process.exitcode is None

    def _healthy(self, method: Callable[[Iterable[object]], bool]) -> bool:
        """Check if all/any of the child processes are healthy."""
        return method(self._pool)

    def _start_process(
        self,
        worker_id: int,
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
                shutdown,
                shutdown_notify,
                work_path,
                self.name,
                worker_id + 1,
                self.timeout,
            ),
            daemon=True,
        )

        with env_var_context(self.env, worker_id):
            coordinator_process.start()

        self._pool[worker_id] = coordinator_process

    def _check(
        self,
        work_path: str,
        shutdown: Event,
        shutdown_notify: Event,
        init: bool,
    ) -> bool:
        """Check and start the worker process if it has not started yet.

        Args:
            work_path: path of working directory
            shutdown: Event of server shutdown
            shutdown_notify: Event of server will shutdown
            init: whether the worker is tried to start at the first time

        Returns:
            Whether the worker is started successfully

        """
        # for every sequential stage
        self._pool = [p if self._process_healthy(p) else None for p in self._pool]
        if self._healthy(all):
            # this stage is healthy
            return True
        if not init and not self._healthy(any):
            # this stage might contain bugs
            return False

        need_start_id = [
            worker_id for worker_id in range(self.num) if self._pool[worker_id] is None
        ]
        for worker_id in need_start_id:
            # for every worker in each stage
            self._start_process(worker_id, work_path, shutdown, shutdown_notify)
        return True

    def _validate(self):
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

    @property
    def worker_count(self) -> int:
        """Get number of workers."""
        return len(self.runtimes)

    @property
    def workers(self) -> List[Type[Worker]]:
        """Get List of workers."""
        return [r.worker for r in self.runtimes]

    def append(self, runtime: Runtime):
        """Sequentially appends workers to the workflow pipeline."""
        self.runtimes.append(runtime)

    def check_and_start(self, init: bool) -> Union[Runtime, None]:
        """Check all worker processes and try to start failed ones.

        Args:
            init: whether the worker is tried to start at the first time

        """
        for worker_runtime in self.runtimes:
            if not worker_runtime._check(  # pylint: disable=protected-access
                self._work_path, self.shutdown, self.shutdown_notify, init
            ):
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

        self.server_path = importlib_files("mosec") / "bin" / "mosec"
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
