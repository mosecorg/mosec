import logging
import time

from pydantic import BaseModel

from mosec import Server, Worker

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    "%(asctime)s - %(process)d - %(levelname)s - %(filename)s:%(lineno)s - %(message)s"
)
sh = logging.StreamHandler()
sh.setFormatter(formatter)
logger.addHandler(sh)


class EchoReq(BaseModel):
    time: float


class EchoResp(BaseModel):
    msg: str


class Preprocess(Worker):
    def forward(self, data: EchoReq):
        logger.debug(f"pre received {data}")
        return data.time


class Inference(Worker):
    def forward(self, data):
        logger.info(f"received batch size: {len(data)}")
        time.sleep(sum(data) / len(data))
        return data


class Postprocess(Worker):
    def forward(self, data) -> EchoResp:
        logger.debug(f"post received {data}")
        return EchoResp(msg=f"sleep {data} seconds")


if __name__ == "__main__":
    server = Server(EchoReq, EchoResp)
    server.append_worker(Preprocess, num=2)
    server.append_worker(Inference, max_batch_size=16)
    server.append_worker(Postprocess, num=2)
    server.run()
