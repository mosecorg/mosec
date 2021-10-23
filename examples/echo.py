import logging
import time

from mosec import Server, Worker
from mosec.errors import ValidationError

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
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
    def forward(self, data: float) -> float:
        logger.info(f"sleeping for {data} seconds")
        time.sleep(data)
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
