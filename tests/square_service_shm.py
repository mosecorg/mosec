from typing import List

from pyarrow import plasma  # type: ignore

from mosec import Server, Worker
from mosec.errors import ValidationError
from mosec.plugins import PlasmaShmWrapper
from mosec.utils import Deferred


class SquareService(Worker):
    def forward(self, data: List[dict]) -> List[dict]:
        try:
            result = [{"x": int(req["x"]) ** 2} for req in data]
        except KeyError as err:
            raise ValidationError(err)
        return result


class DummyPostprocess(Worker):
    """This dummy stage is added to test the shm IPC"""

    def forward(self, data: dict) -> dict:
        return data


if __name__ == "__main__":
    # initialize a 20Mb object store as shared memory
    with plasma.start_plasma_store(plasma_store_memory=20 * 1000 * 1000) as (
        shm_path,
        shm_process,
    ):
        server = Server(
            ipc_wrapper=Deferred(  # defer the wrapper init to worker processes
                PlasmaShmWrapper,
                shm_path=shm_path,
            )
        )
        server.register_daemon("plasma_server", shm_process)
        server.append_worker(SquareService, max_batch_size=8)
        server.append_worker(DummyPostprocess, num=2)
        server.run()
