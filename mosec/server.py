import logging
import multiprocessing as mp
from typing import List, Union

from pydantic import BaseSettings

from .coordinator import STAGE_EGRESS, STAGE_INGRESS, STAGE_INTERNAL, Coordinator
from .utils import validate_input
from .worker import Worker

logger = logging.getLogger(__name__)


class CommSettings(BaseSettings):
    socket_prefix: str


class CtrSettings(BaseSettings):
    waitUtil: str


class CoordSettings(BaseSettings):
    waitUtil: str


class Settings(BaseSettings):
    common: CommSettings = CommSettings(socket_prefix="/tmp/mosec/")
    controller: CtrSettings = CtrSettings()
    coordinator: CoordSettings = CoordSettings()


class Server:
    def __init__(self):
        self._req_schema = None
        self._resp_schema = None

        self._worker_cls = []
        self._worker_num = []
        self._worker_mbs = []

        self._coordinator_ctx = []
        self._coordinator_pools = []

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
        ):  # sequential stages
            for worker_id in range(len(w_num)):
                # multiple workers
                shutdown = mp.get_context(c_ctx).Event()
                worker_process = mp.get_context(c_ctx).Process(
                    target=Coordinator,
                    args=(
                        w_cls,
                        w_mbs,
                        STAGE_INGRESS
                        if stage_id == 0
                        else STAGE_EGRESS
                        if stage_id == len(self._worker_cls) - 1
                        else STAGE_INTERNAL,
                        shutdown,
                        self._configs["common"]["socket_prefix"],
                        stage_id,
                        worker_id,
                        self._req_schema if stage_id == 0 else None,
                        self._resp_schema
                        if stage_id == len(self._worker_cls) - 1
                        else None,
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

    def set_req_schema(self, schema):
        self._req_schema = schema

    def set_resp_schema(self, schema):
        self._resp_schema = schema

    def append_worker(
        self,
        worker: Union[Worker, List[Worker]],
        num: int = 1,
        max_batch_size: int = 1,
        start_method: str = "spawn",
    ):
        validate_input(
            self.append_worker,
            worker=worker,
            num=num,
            max_batch_size=max_batch_size,
            start_method=start_method,
        )
        assert num > 0, "worker number must be at least 1"
        assert max_batch_size > 0, "maximum batch size must be at least 1"

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
