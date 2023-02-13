# Copyright 2022 MOSEC Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Example: Sample structures for using mosec server."""

import logging
import time
from typing import List

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
    """Sample Class."""

    def forward(self, data: dict) -> float:
        logger.debug("pre received %s", data)
        # Customized, simple input validation
        try:
            count_time = float(data["time"])
        except KeyError as err:
            raise ValidationError(f"cannot find key {err}") from err
        return count_time


class Inference(Worker):
    """Sample Class."""

    def forward(self, data: List[float]) -> List[float]:
        logger.info("sleeping for %s seconds", sum(data))
        time.sleep(max(data))
        return data


class Postprocess(Worker):
    """Sample Class."""

    def forward(self, data: float) -> dict:
        logger.debug("post received %f", data)
        return {"msg": f"sleep {data} seconds"}


if __name__ == "__main__":
    server = Server()
    server.append_worker(Preprocess)
    server.append_worker(Inference, max_batch_size=32)
    server.append_worker(Postprocess)
    server.run()
