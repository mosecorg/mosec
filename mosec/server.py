import logging
import multiprocessing as mp
import signal
import subprocess
from multiprocessing.synchronize import Event
from pathlib import Path
from time import sleep
from typing import List, Tuple, Type, Union

import pkg_resources
from pydantic import BaseModel, BaseSettings, conint, validate_arguments

from .coordinator import STAGE_EGRESS, STAGE_INGRESS, Coordinator
from .utils import SettingCtx, Settings
from .worker import Worker

logger = logging.getLogger(__name__)

AtLeastOne: Type[int] = conint(strict=True, ge=1)

GUARD_CHECK_INTERVAL = 1


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

        self._controller_process: mp.Process

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
        pass

    def _start_controller(self):
        """Subprocess to start controller program"""
        with SettingCtx():
            path = Path(pkg_resources.resource_filename("mosec", "bin"), "mosec")
            self._controller_process = subprocess.Popen([path])

    def _terminate(self, signum, framestack):
        """Graceful shutdown"""
        logger.info(f"[{signum}] terminates server [{framestack}]")
        # terminate controller first and wait for a waittime
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
        return (processes, events)

    def _spawn_coordinators_guard(self):
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

                if None not in self._coordinator_pools[stage_id]:
                    continue
                stage = ""
                stage += STAGE_INGRESS if stage_id == 0 else ""
                stage += STAGE_EGRESS if stage_id == len(self._worker_cls) - 1 else ""
                req_schema = self._req_schema if stage_id == 0 else None
                resp_schema = (
                    self._resp_schema if stage_id == len(self._worker_cls) - 1 else None
                )
                for worker_id in range(len(w_num)):
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
            ctr_exitcode = self._controller_process.poll()
            if ctr_exitcode:
                self._terminate(ctr_exitcode, "serving service is dead")
            sleep(GUARD_CHECK_INTERVAL)

    def _combine_workers(self, workers: List[Type[Worker]]) -> Type[Worker]:
        pass

    @validate_arguments
    def append_worker(
        self,
        worker: Union[Type[Worker], List[Type[Worker]]],
        num: AtLeastOne = 1,  # type: ignore
        max_batch_size: AtLeastOne = 1,  # type: ignore
        start_method: str = "spawn",
    ):
        assert start_method in {
            "spawn",
            "fork",
        }, "start method needs to be one of {'spawn', 'fork'}"

        if isinstance(worker, list):
            worker = self._combine_workers(worker)
        self._worker_cls.append(worker)
        self._worker_num.append(num)
        self._worker_mbs.append(max_batch_size)
        self._coordinator_ctx.append(start_method)
        self._coordinator_pools.append([None] * num)
        self._coordinator_shutdown.append([None] * num)

    def run(self):
        self._validate()
        self._parse_args()
        self._start_controller()
        self._spawn_coordinators_guard()
