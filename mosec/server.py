import logging
import multiprocessing as mp
from typing import List, Type, Union

from pydantic import BaseModel, BaseSettings, conint, validate_arguments

from .coordinator import STAGE_EGRESS, STAGE_INGRESS, Coordinator
from .worker import Worker

logger = logging.getLogger(__name__)

AtLeastOne: Type[int] = conint(strict=True, ge=1)


class Settings(BaseSettings):
    socket_prefix: str = "/tmp/mosec/"
    waitUtil: str = "10ms"


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
        self._coordinator_pools: List[List[mp.Process]] = []

        self._configs = Settings()

    def _parse_args(self):
        pass  # directly update self._configs

    def _spawn_coordinators(self):
        for stage_id, (w_cls, w_num, w_mbs, c_ctx) in enumerate(
            zip(
                self._worker_cls,
                self._worker_num,
                self._worker_mbs,
                self._coordinator_ctx,
            )
        ):
            # sequential stages
            stage = ""
            stage += STAGE_INGRESS if stage_id == 0 else ""
            stage += STAGE_EGRESS if stage_id == len(self._worker_cls) - 1 else ""
            req_schema = self._req_schema if stage_id == 0 else None
            resp_schema = (
                self._resp_schema if stage_id == len(self._worker_cls) - 1 else None
            )
            for worker_id in range(len(w_num)):
                # multiple workers
                shutdown = mp.get_context(c_ctx).Event()
                worker_process = mp.get_context(c_ctx).Process(
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
                )
                self._coordinator_pools[stage_id].append(worker_process)

        for w in (
            worker
            for workers_same_stage in self._coordinator_pools
            for worker in workers_same_stage
        ):
            w.start()

    def _manage_coordinators(self):
        pass

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
        self._coordinator_pools.append([])

    def run(self):
        self._parse_args()
        self._init_controller()
        self._spawn_coordinators()
        self._manage_coordinators()
