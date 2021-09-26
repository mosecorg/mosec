from typing import List

from pydantic import BaseModel

from mosec import Server, Worker


class Req(BaseModel):
    x: int


class Resp(BaseModel):
    x: int


class SquareService(Worker):
    def forward(self, data: List[Req]) -> List[Resp]:
        return [Resp(x=req.x ** 2) for req in data]


if __name__ == "__main__":
    server = Server(Req, Resp)
    server.append_worker(SquareService, max_batch_size=8)
    server.run()
