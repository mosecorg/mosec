import logging
import multiprocessing as mp
import signal
import subprocess
from multiprocessing.synchronize import Event
from pathlib import Path
from time import monotonic, sleep
from typing import List, Optional, Tuple, Type, Union

import pkg_resources
from pydantic import BaseModel, BaseSettings, conint, validate_arguments

from .coordinator import STAGE_EGRESS, STAGE_INGRESS, Coordinator
from .utils import Settings
from .worker import Worker

logger = logging.getLogger(__name__)

AtLeastOne: Type[int] = conint(strict=True, ge=1)

GUARD_CHECK_INTERVAL = 1
NEW_PROCESS_METHOD = {"spawn", "fork"}


class Server:
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
        self._coordinator_shutdown: List[List[Union[Event, None]]] = []

        self._controller_process: Optional[mp.Process] = None

        self._configs: BaseSettings = Settings()

        self._server_shutdown: bool = False
        signal.signal(signal.SIGTERM, self._terminate)
        signal.signal(signal.SIGINT, self._terminate)

    def _validate(self):
        assert len(self._worker_cls) > 0, (
            "no worker registered\n"
            "help: use `.append_worker(...)` to register at least one worker"
        )

    def _parse_args(self):
        # directly update self._configs
        # serialize configs into env for controller to read
        pass  # TODO

    def _start_controller(self):
        """Subprocess to start controller program"""
        if not self._server_shutdown:
            path = Path(pkg_resources.resource_filename("mosec", "bin"), "mosec")
            self._controller_process = subprocess.Popen([path])

    def _terminate(self, signum, framestack):
        logger.info(f"[{signum}] terminating server [{framestack}] ...")
        self._server_shutdown = True

    @staticmethod
    def _clean_pools(
        processes: List[Union[mp.Process, None]],
        events: List[Union[Event, None]],
    ) -> Tuple[List[Union[mp.Process, None]], List[Union[Event, None]]]:
        for i, (p, e) in enumerate(zip(processes, events)):
            if p is None or p.exitcode is not None:
                processes[i] = None
                events[i] = None
        return processes, events

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
                (
                    self._coordinator_pools[stage_id],
                    self._coordinator_shutdown[stage_id],
                ) = self._clean_pools(
                    self._coordinator_pools[stage_id],
                    self._coordinator_shutdown[stage_id],
                )

                if all(self._coordinator_pools[stage_id]):
                    # this stage is healthy
                    continue

                if not first and not any(self._coordinator_pools[stage_id]):
                    # this stage might contain bugs
                    self._terminate(
                        1,
                        f"all workers at stage {stage_id+1} exited;"
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
                    shutdown = mp.get_context(c_ctx).Event()
                    coordinator_process = mp.get_context(c_ctx).Process(
                        target=Coordinator,
                        args=(
                            w_cls,
                            w_mbs,
                            stage,
                            shutdown,
                            self._configs.socket_prefix,
                            stage_id,
                            worker_id,
                            req_schema,
                            resp_schema,
                        ),
                        daemon=True,
                    )
                    coordinator_process.start()
                    self._coordinator_pools[stage_id][worker_id] = coordinator_process
                    self._coordinator_shutdown[stage_id][worker_id] = shutdown
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
        # terminate controller first and wait for a graceful period
        if self._controller_process:
            self._controller_process.terminate()
            graceful_period = monotonic() + self._configs.timeout / 1000
            while monotonic() < graceful_period:
                ctr_exitcode = self._controller_process.poll()
                if ctr_exitcode:
                    self._terminate(
                        ctr_exitcode,
                        f"mosec controller halted on error: {ctr_exitcode}",
                    )
                    break
                sleep(0.1)

        for shutdown_events in self._coordinator_shutdown:
            for event in shutdown_events:
                if event:
                    event.set()
        logger.info("mosec server exited. see you.")

    @validate_arguments
    def append_worker(
        self,
        worker: Type[Worker],
        num: AtLeastOne = 1,  # type: ignore
        max_batch_size: AtLeastOne = 1,  # type: ignore
        start_method: str = "spawn",
    ):
        """Sequentially add workers to be invoked in a pipelined manner"""
        assert (
            start_method in NEW_PROCESS_METHOD
        ), f"start method needs to be one of {NEW_PROCESS_METHOD}"

        self._worker_cls.append(worker)
        self._worker_num.append(num)
        self._worker_mbs.append(max_batch_size)
        self._coordinator_ctx.append(start_method)
        self._coordinator_pools.append([None] * num)
        self._coordinator_shutdown.append([None] * num)

    def run(self):
        """Run the mosec model server!"""
        self._validate()
        self._parse_args()
        self._start_controller()
        self._manage_coordinators()
        self._halt()
