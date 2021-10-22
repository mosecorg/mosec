import logging
from time import sleep

from mosec import Server, Worker
from mosec.errors import ValidationError

logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter(
    "%(asctime)s - %(process)d - %(levelname)s - %(filename)s:%(lineno)s - %(message)s"
)
sh = logging.StreamHandler()
sh.setFormatter(formatter)
logger.addHandler(sh)


class Preprocess(Worker):
    def forward(self, data: dict) -> float:
        logger.debug(f"pre received {data}")
        # Customized, simple input validation
        try:
            time = float(data["time"])
        except KeyError as err:
            raise ValidationError(f"cannot find key {err}")
        return time


class Inference(Worker):
    example = 2.0  # override `example` (the same data format as the input of `forward`)

    def __init__(self):
        super().__init__()
        sleep(1)  # mock some time-comsuming data loading, etc.
        self.first = True

    def forward(self, data: float) -> float:
        if self.first:
            sleep(5)  # mock first time model forward
            self.first = False
        logger.info(f"sleeping for {data} seconds")
        sleep(data)
        return data


class Postprocess(Worker):
    def forward(self, data: float) -> dict:
        logger.debug(f"post received {data}")
        return {"msg": f"sleep {data} seconds"}


if __name__ == "__main__":
    server = Server()
    server.append_worker(Preprocess)
    server.append_worker(Inference)
    server.append_worker(Postprocess)
    server.run()
