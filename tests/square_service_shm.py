from typing import List

from mosec import Server, Worker
from mosec.errors import ValidationError


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
    server = Server(plasma_shm=1000 * 1000 * 20)
    server.append_worker(SquareService, max_batch_size=8)
    server.append_worker(DummyPostprocess, num=2)
    server.run()
