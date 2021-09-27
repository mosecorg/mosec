import logging
import multiprocessing as mp
import signal
import subprocess
import traceback
from multiprocessing.synchronize import Event
from os.path import exists
from pathlib import Path
from shutil import rmtree
from time import monotonic, sleep
from typing import List, Optional, Type, Union

import pkg_resources
from pydantic import BaseModel, conint, validate_arguments

from .args import ArgParser
from .coordinator import STAGE_EGRESS, STAGE_INGRESS, Coordinator
from .worker import Worker

logger = logging.getLogger(__name__)

AtLeastOne: Type[int] = conint(strict=True, ge=1)

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
    """

    def __init__(
        self, req_schema: Type[BaseModel] = None, resp_schema: Type[BaseModel] = None
    ):
        self._req_schema = req_schema
        self._resp_schema = resp_schema

        self._worker_cls: List[Type[Worker]] = []
        self._worker_num: List[AtLeastOne] = []  # type: ignore
        self._worker_mbs: List[AtLeastOne] = []  # type: ignore

        self._coordinator_ctx: List[str] = []
        self._coordinator_pools: List[List[Union[mp.Process, None]]] = []
        self._coordinator_shutdown: Event = mp.get_context("spawn").Event()
        self._coordinator_shutdown_notify: Event = mp.get_context("spawn").Event()

        self._controller_process: Optional[mp.Process] = None

        self._configs: dict = {}

        self._server_shutdown: bool = False
        signal.signal(signal.SIGTERM, self._terminate)
        signal.signal(signal.SIGINT, self._terminate)

    def _validate(self):
        assert len(self._worker_cls) > 0, (
            "no worker registered\n"
            "help: use `.append_worker(...)` to register at least one worker"
        )

    def _parse_args(self):
        self._configs = vars(ArgParser.parse())
        logger.info(f"Mosec Server Configurations: {self._configs}")

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
            for stage_id, (w_cls, w_num, w_mbs, c_ctx) in enumerate(
                zip(
                    self._worker_cls,
                    self._worker_num,
                    self._worker_mbs,
                    self._coordinator_ctx,
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
                    req_schema = self._req_schema
                else:
                    req_schema = None
                if stage_id == len(self._worker_cls) - 1:
                    stage += STAGE_EGRESS
                    resp_schema = self._resp_schema
                else:
                    resp_schema = None

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
                            req_schema,
                            resp_schema,
                        ),
                        daemon=True,
                    )
                    coordinator_process.start()
                    self._coordinator_pools[stage_id][worker_id] = coordinator_process
            first = False
            if self._controller_process:
                ctr_exitcode = self._controller_process.poll()
                if ctr_exitcode:
                    self._terminate(
                        ctr_exitcode,
                        f"mosec controller exited on error: {ctr_exitcode}",
                    )
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

    @validate_arguments
    def append_worker(
        self,
        worker: Type[Worker],
        num: AtLeastOne = 1,  # type: ignore
        max_batch_size: AtLeastOne = 1,  # type: ignore
        start_method: str = "spawn",
    ):
        """
        This method sequentially appends workers to the workflow pipeline.

        Arguments:
            worker: the class you inherit from `Worker` which implements
                the `forward` method
            num: the number of processes for parallel computing (>=1)
            max_batch_size: the maximum batch size allowed (>=1)
            start_method: the process starting method ("spawn" or "fork")
        """
        assert (
            start_method in NEW_PROCESS_METHOD
        ), f"start method needs to be one of {NEW_PROCESS_METHOD}"

        self._worker_cls.append(worker)
        self._worker_num.append(num)
        self._worker_mbs.append(max_batch_size)
        self._coordinator_ctx.append(start_method)
        self._coordinator_pools.append([None] * num)

    def run(self):
        """
        This method starts the mosec model server!
        """
        self._validate()
        self._parse_args()
        self._start_controller()
        try:
            self._manage_coordinators()
        except Exception:
            logger.error(traceback.format_exc().replace("\n", " "))
        self._halt()
