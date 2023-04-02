# Copyright 2022 MOSEC Authors
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

"""MOSEC server interface.

This module provides a way to define the service components for machine learning
model serving.

Dynamic Batching
================

    The user may enable the dynamic batching feature for any stage when the
    corresponding worker is appended, by setting the
    :py:meth:`append_worker(max_batch_size) <Server.append_worker>`.

Multiprocess
============

    The user may spawn multiple processes for any stage when the
    corresponding worker is appended, by setting the
    :py:meth:`append_worker(num) <Server.append_worker>`.

IPC Wrapper
===========

    The user may wrap the inter-process communication to use shared memory,
    e.g. pyarrow plasma, by providing the :py:mod:`IPC Wrapper <mosec.ipc.IPCWrapper>`
    for the server.
"""

import multiprocessing as mp
import shutil
import signal
import subprocess
import traceback
from functools import partial
from multiprocessing.synchronize import Event
from pathlib import Path
from time import monotonic, sleep
from typing import Dict, List, Optional, Type, Union

import pkg_resources

from mosec.args import mosec_args
from mosec.coordinator import STAGE_EGRESS, STAGE_INGRESS, Coordinator
from mosec.dry_run import DryRunner
from mosec.env import env_var_context
from mosec.ipc import IPCWrapper
from mosec.log import get_internal_logger
from mosec.worker import Worker

logger = get_internal_logger()


GUARD_CHECK_INTERVAL = 1
NEW_PROCESS_METHOD = {"spawn", "fork"}


class Server:
    """MOSEC server interface.

    It allows users to sequentially append workers they implemented, builds
    the workflow pipeline automatically and starts up the server.
    """

    # pylint: disable=too-many-instance-attributes
    def __init__(
        self,
        ipc_wrapper: Optional[Union[IPCWrapper, partial]] = None,
    ):
        """Initialize a MOSEC Server.

        Args:
            ipc_wrapper: wrapper function (before and after) IPC
        """
        self.ipc_wrapper = ipc_wrapper

        self._worker_cls: List[Type[Worker]] = []
        self._worker_num: List[int] = []
        self._worker_mbs: List[int] = []
        self._worker_wait: List[int] = []
        self._worker_timeout: List[int] = []

        self._coordinator_env: List[Union[None, List[Dict[str, str]]]] = []
        self._coordinator_ctx: List[str] = []
        self._coordinator_pools: List[List[Union[mp.Process, None]]] = []
        self._coordinator_shutdown: Event = mp.get_context("spawn").Event()
        self._coordinator_shutdown_notify: Event = mp.get_context("spawn").Event()

        self._controller_process: Optional[subprocess.Popen] = None

        self._daemon: Dict[str, Union[subprocess.Popen, mp.Process]] = {}

        self._configs: dict = vars(mosec_args)

        self._server_shutdown: bool = False

    def _handle_signal(self):
        signal.signal(signal.SIGTERM, self._terminate)
        signal.signal(signal.SIGINT, self._terminate)

    def _validate_server(self):
        assert len(self._worker_cls) > 0, (
            "no worker registered\n"
            "help: use `.append_worker(...)` to register at least one worker"
        )

    @staticmethod
    def _validate_arguments(
        worker,
        num,
        max_batch_size,
        max_wait_time,
        start_method,
        env,
        timeout,
    ):
        def validate_int_ge(number, name, threshold=1):
            assert isinstance(
                number, int
            ), f"{name} must be integer but you give {type(number)}"
            assert number >= threshold, f"{name} must be no less than {threshold}"

        def validate_env():
            if env is None:
                return

            def validate_str_dict(dictionary: Dict):
                for key, value in dictionary.items():
                    if not (isinstance(key, str) and isinstance(value, str)):
                        return False
                return True

            assert len(env) == num, "len(env) must equal to num"
            valid = True
            if not isinstance(env, List):
                valid = False
            elif not all(isinstance(x, Dict) and validate_str_dict(x) for x in env):
                valid = False
            assert valid, "env must be a list of string dictionary"

        validate_env()
        assert issubclass(worker, Worker), "worker must be inherited from mosec.Worker"
        validate_int_ge(num, "worker number")
        validate_int_ge(max_batch_size, "maximum batch size")
        validate_int_ge(max_wait_time, "maximum wait time", 0)
        validate_int_ge(timeout, "forward timeout", 0)
        assert (
            start_method in NEW_PROCESS_METHOD
        ), f"start method must be one of {NEW_PROCESS_METHOD}"

    def _check_daemon(self):
        for name, proc in self._daemon.items():
            if proc is None:
                continue
            code = None
            if isinstance(proc, mp.Process):
                code = proc.exitcode
            elif isinstance(proc, subprocess.Popen):
                code = proc.poll()

            if code is not None:
                self._terminate(
                    code,
                    f"mosec daemon [{name}] exited on error code: {code}",
                )

    def _controller_args(self):
        args = []
        self._configs.pop("dry_run")
        for key, value in self._configs.items():
            args.extend([f"--{key}", str(value).lower()])
        for batch_size in self._worker_mbs:
            args.extend(["--batches", str(batch_size)])
        for wait_time in self._worker_wait:
            args.extend(
                ["--waits", str(wait_time if wait_time else self._configs["wait"])]
            )
        logger.info("mosec received arguments: %s", args)
        return args

    def _start_controller(self):
        """Subprocess to start controller program."""
        if not self._server_shutdown:
            path = Path(pkg_resources.resource_filename("mosec", "bin"), "mosec")
            # pylint: disable=consider-using-with
            self._controller_process = subprocess.Popen(
                [path] + self._controller_args()
            )
            self.register_daemon("controller", self._controller_process)

    def _terminate(self, signum, framestack):
        logger.info("received signum[%s], terminating server [%s]", signum, framestack)
        self._server_shutdown = True

    @staticmethod
    def _clean_pools(
        processes: List[Union[mp.Process, None]],
    ) -> List[Union[mp.Process, None]]:
        for i, process in enumerate(processes):
            if process is None or process.exitcode is not None:
                processes[i] = None
        return processes

    def _manage_coordinators(self):
        first = True
        while not self._server_shutdown:
            for stage_id, (w_cls, w_num, w_mbs, w_timeout, c_ctx, c_env) in enumerate(
                zip(
                    self._worker_cls,
                    self._worker_num,
                    self._worker_mbs,
                    self._worker_timeout,
                    self._coordinator_ctx,
                    self._coordinator_env,
                )
            ):
                # for every sequential stage
                self._coordinator_pools[stage_id] = self._clean_pools(
                    self._coordinator_pools[stage_id]
                )

                if all(self._coordinator_pools[stage_id]):
                    # this stage is healthy
                    continue

                if not first and not any(self._coordinator_pools[stage_id]):
                    # this stage might contain bugs
                    self._terminate(
                        1,
                        f"all the {w_cls.__name__} workers at stage {stage_id} exited;"
                        " please check for bugs or socket connection issues",
                    )
                    break

                stage = ""
                if stage_id == 0:
                    stage += STAGE_INGRESS
                if stage_id == len(self._worker_cls) - 1:
                    stage += STAGE_EGRESS

                for worker_id in range(w_num):
                    # for every worker in each stage
                    if self._coordinator_pools[stage_id][worker_id] is not None:
                        continue

                    coordinator_process = mp.get_context(c_ctx).Process(  # type: ignore
                        target=Coordinator,
                        args=(
                            w_cls,
                            w_mbs,
                            stage,
                            self._coordinator_shutdown,
                            self._coordinator_shutdown_notify,
                            self._configs["path"],
                            stage_id + 1,
                            worker_id + 1,
                            self.ipc_wrapper,
                            w_timeout,
                        ),
                        daemon=True,
                    )

                    with env_var_context(c_env, worker_id):
                        coordinator_process.start()

                    self._coordinator_pools[stage_id][worker_id] = coordinator_process
            first = False
            self._check_daemon()
            sleep(GUARD_CHECK_INTERVAL)

    def _halt(self):
        """Graceful shutdown."""
        # notify coordinators for the shutdown
        self._coordinator_shutdown_notify.set()

        # terminate controller first and wait for a graceful period
        if self._controller_process is not None:
            self._controller_process.terminate()
            graceful_period = monotonic() + self._configs["timeout"] / 1000
            while monotonic() < graceful_period:
                ctr_exitcode = self._controller_process.poll()
                if ctr_exitcode is not None:  # exited
                    if ctr_exitcode:  # on error
                        logger.error("mosec service halted on error [%d]", ctr_exitcode)
                    else:
                        logger.info("mosec service halted normally [%d]", ctr_exitcode)
                    break
                sleep(0.1)

            if monotonic() > graceful_period:
                logger.error("failed to terminate mosec service, will try to kill it")
                self._controller_process.kill()

        # shutdown coordinators
        self._coordinator_shutdown.set()
        shutil.rmtree(self._configs["path"], ignore_errors=True)
        logger.info("mosec exited normally")

    def register_daemon(self, name: str, proc: subprocess.Popen):
        """Register a daemon to be monitored.

        Args:
            name: the name of this daemon
            proc: the process handle of the daemon
        """
        assert isinstance(name, str), "daemon name should be a string"
        assert isinstance(
            proc, (mp.Process, subprocess.Popen)
        ), f"{type(proc)} is not a process or subprocess"
        self._daemon[name] = proc

    # pylint: disable=too-many-arguments
    def append_worker(
        self,
        worker: Type[Worker],
        num: int = 1,
        max_batch_size: int = 1,
        max_wait_time: int = 0,
        start_method: str = "spawn",
        env: Union[None, List[Dict[str, str]]] = None,
        timeout: int = 0,
    ):
        """Sequentially appends workers to the workflow pipeline.

        Args:
            worker: the class you inherit from :class:`Worker<mosec.worker.Worker>`
                which implements the :py:meth:`forward<mosec.worker.Worker.forward>`
            num: the number of processes for parallel computing (>=1)
            max_batch_size: the maximum batch size allowed (>=1), will enable the
                dynamic batching if it > 1
            max_wait_time: the maximum wait time (millisecond) for dynamic batching,
                needs to be used with `max_batch_size` to enable the feature. If not
                configure, will use the CLI argument `--wait` (default=10ms)
            start_method: the process starting method ("spawn" or "fork")
            env: the environment variables to set before starting the process
            timeout: the timeout (second) for each worker forward processing (>=1)
        """
        self._validate_arguments(
            worker, num, max_batch_size, max_wait_time, start_method, env, timeout
        )
        self._worker_cls.append(worker)
        self._worker_num.append(num)
        self._worker_mbs.append(max_batch_size)
        self._worker_wait.append(max_wait_time)
        self._worker_timeout.append(
            timeout if timeout >= 1 else self._configs["timeout"] // 1000
        )
        self._coordinator_env.append(env)
        self._coordinator_ctx.append(start_method)
        self._coordinator_pools.append([None] * num)

    def run(self):
        """Start the mosec model server."""
        self._validate_server()
        if self._configs["dry_run"]:
            DryRunner(
                self._worker_cls,
                self._worker_mbs,
                self._coordinator_env,
            ).run()
            return

        self._handle_signal()
        self._start_controller()
        try:
            self._manage_coordinators()
        # pylint: disable=broad-except
        except Exception:
            logger.error(traceback.format_exc().replace("\n", " "))
        self._halt()
