import contextlib
import logging
import multiprocessing as mp
import os
import signal
import subprocess
import traceback
from functools import partial
from multiprocessing.synchronize import Event
from os.path import exists
from pathlib import Path
from shutil import rmtree
from time import monotonic, sleep
from typing import Dict, List, Optional, Type, Union

import pkg_resources

from .args import ArgParser
from .coordinator import STAGE_EGRESS, STAGE_INGRESS, Coordinator
from .ipc import IPCWrapper
from .worker import Worker

logger = logging.getLogger(__name__)


GUARD_CHECK_INTERVAL = 1
NEW_PROCESS_METHOD = {"spawn", "fork"}


class Server:
    """
    This public class defines the mosec server interface. It allows
    users to sequentially append workers they implemented, builds
    the workflow pipeline automatically and starts up the server.

    ###### Batching
    > The user may enable the batching feature for any stage when the
    corresponding worker is appended, by setting the `max_batch_size`.

    ###### Multiprocess
    > The user may spawn multiple processes for any stage when the
    corresponding worker is appended, by setting the `num`.

    ###### IPC Wrapper
    > The user may wrap the inter-process communication to use shared memory,
    e.g. pyarrow plasma, by providing the IPC wrapper for the server.
    """

    def __init__(
        self,
        ipc_wrapper: Optional[Union[IPCWrapper, partial]] = None,
    ):
        """Initialize a MOSEC Server

        Args:
            ipc_wrapper (Optional[Union[IPCWrapper, partial]], optional):
                IPCWrapper class. Defaults to None.
        """
        self.ipc_wrapper = ipc_wrapper

        self._worker_cls: List[Type[Worker]] = []
        self._worker_num: List[int] = []
        self._worker_mbs: List[int] = []

        self._coordinator_env: List[Union[None, List[Dict[str, str]]]] = []
        self._coordinator_ctx: List[str] = []
        self._coordinator_pools: List[List[Union[mp.Process, None]]] = []
        self._coordinator_shutdown: Event = mp.get_context("spawn").Event()
        self._coordinator_shutdown_notify: Event = mp.get_context("spawn").Event()

        self._controller_process: Optional[subprocess.Popen] = None

        self._daemon: Dict[str, Union[subprocess.Popen, mp.Process]] = {}

        self._configs: dict = {}

        self._server_shutdown: bool = False
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
        start_method,
        env,
    ):
        def validate_int_ge_1(number, name):
            assert isinstance(
                number, int
            ), f"{name} must be integer but you give {type(number)}"
            assert number >= 1, f"{name} must be greater than 1"

        def validate_env():
            if env is None:
                return

            def validate_str_dict(dictionary: Dict):
                for k, v in dictionary.items():
                    if not (isinstance(k, str) and isinstance(v, str)):
                        return False
                return True

            assert len(env) == num, "len(env) must equal to num"
            valid = True
            if not isinstance(env, List):
                valid = False
            elif not all([isinstance(x, Dict) and validate_str_dict(x) for x in env]):
                valid = False
            assert valid, "env must be a list of string dictionary"

        validate_env()
        assert issubclass(worker, Worker), "worker must be inherited from mosec.Worker"
        validate_int_ge_1(num, "worker number")
        validate_int_ge_1(max_batch_size, "maximum batch size")
        assert (
            start_method in NEW_PROCESS_METHOD
        ), f"start method must be one of {NEW_PROCESS_METHOD}"

    def _parse_args(self):
        self._configs = vars(ArgParser.parse())
        logger.info(f"Mosec Server Configurations: {self._configs}")

    def _check_daemon(self):
        for name, proc in self._daemon.items():
            if proc is not None:
                terminate = False
                if isinstance(proc, mp.Process):
                    code = proc.exitcode
                elif isinstance(proc, subprocess.Popen):
                    code = proc.poll()
                if code:
                    terminate = True

                if terminate:
                    self._terminate(
                        code,
                        f"mosec daemon [{name}] exited on error code: {code}",
                    )

    def _controller_args(self):
        args = []
        for k, v in self._configs.items():
            args.extend([f"--{k}", str(v)])
        args.extend(["--batches"] + list(map(str, self._worker_mbs)))
        return args

    def _start_controller(self):
        """Subprocess to start controller program"""
        if not self._server_shutdown:
            path = self._configs["path"]
            if exists(path):
                logger.info(f"path already exists, try to remove it: {path}")
                rmtree(path)
            path = Path(pkg_resources.resource_filename("mosec", "bin"), "mosec")
            self._controller_process = subprocess.Popen(
                [path] + self._controller_args()
            )
            self.register_daemon("controller", self._controller_process)

    def _terminate(self, signum, framestack):
        logger.info(f"[{signum}] terminating server [{framestack}] ...")
        self._server_shutdown = True

    @staticmethod
    def _clean_pools(
        processes: List[Union[mp.Process, None]],
    ) -> List[Union[mp.Process, None]]:
        for i, p in enumerate(processes):
            if p is None or p.exitcode is not None:
                processes[i] = None
        return processes

    def _manage_coordinators(self):
        first = True
        while not self._server_shutdown:
            for stage_id, (w_cls, w_num, w_mbs, c_ctx, c_env) in enumerate(
                zip(
                    self._worker_cls,
                    self._worker_num,
                    self._worker_mbs,
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
                        f"all workers at stage {stage_id} exited;"
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

                    coordinator_process = mp.get_context(c_ctx).Process(
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
        """Graceful shutdown"""
        # notify coordinators for the shutdown
        self._coordinator_shutdown_notify.set()

        # terminate controller first and wait for a graceful period
        if self._controller_process:
            self._controller_process.terminate()
            graceful_period = monotonic() + self._configs["timeout"] / 1000
            while monotonic() < graceful_period:
                ctr_exitcode = self._controller_process.poll()
                if ctr_exitcode is not None:  # exited
                    if ctr_exitcode:  # on error
                        logger.error(
                            f"mosec controller halted on error: {ctr_exitcode}"
                        )
                    else:
                        logger.info("mosec controller halted normally")
                    break
                sleep(0.1)

        # shutdown coordinators
        self._coordinator_shutdown.set()

        logger.info("mosec server exited. see you.")

    def register_daemon(self, name: str, proc: mp.Process):
        """This method registers a daemon to be monitored.

        Args:
            name (str): the name of this daemon
            proc (mp.Process): the process handle of the daemon
        """
        assert isinstance(name, str), "daemon name should be a string"
        assert isinstance(
            proc, (mp.Process, subprocess.Popen)
        ), f"{type(proc)} is not a process or subprocess"
        self._daemon[name] = proc

    def append_worker(
        self,
        worker: Type[Worker],
        num: int = 1,
        max_batch_size: int = 1,
        start_method: str = "spawn",
        env: Union[None, List[Dict[str, str]]] = None,
    ):
        """
        This method sequentially appends workers to the workflow pipeline.

        Arguments:
            worker: the class you inherit from `Worker` which implements
                the `forward` method
            num: the number of processes for parallel computing (>=1)
            max_batch_size: the maximum batch size allowed (>=1)
            start_method: the process starting method ("spawn" or "fork")
            env: the environment variables to set before starting the process
        """
        self._validate_arguments(worker, num, max_batch_size, start_method, env)
        self._worker_cls.append(worker)
        self._worker_num.append(num)
        self._worker_mbs.append(max_batch_size)
        self._coordinator_env.append(env)
        self._coordinator_ctx.append(start_method)
        self._coordinator_pools.append([None] * num)

    def run(self):
        """
        This method starts the mosec model server!
        """
        self._validate_server()
        self._parse_args()
        self._start_controller()
        try:
            self._manage_coordinators()
        except Exception:
            logger.error(traceback.format_exc().replace("\n", " "))
        self._halt()


@contextlib.contextmanager
def env_var_context(env: Union[None, List[Dict[str, str]]], id: int):
    default: Dict = {}
    try:
        if env is not None:
            for k, v in env[id].items():
                default[k] = os.getenv(k, "")
                os.environ[k] = v
        yield None
    finally:
        for k, v in default.items():
            os.environ[k] = v
