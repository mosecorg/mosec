# Copyright 2023 MOSEC Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Simulate bad requests:

- Preprocess: raise ValidationError
- Inference: raise random ServerError
- client: disconnection
"""

import time
from random import random
from typing import List

from mosec import Server, ServerError, ValidationError, Worker, get_logger

logger = get_logger()
LUCKY_THRESHOLD = 0.5


class Preprocess(Worker):
    """Sample Class."""

    def forward(self, data: dict) -> float:
        logger.debug("pre received %s", data)
        try:
            count_time = float(data["time"])
        except KeyError as err:
            raise ValidationError(f"cannot find key {err}") from err
        return count_time


class Inference(Worker):
    """Sample Class."""

    def forward(self, data: List[float]) -> List[float]:
        # special case: {"time": 0}
        if len(data) == 1 and data[0] == 0:
            return data
        # chaos
        if random() < LUCKY_THRESHOLD:
            logger.info("bad luck, this batch will be drop")
            raise ServerError("no way")
        logger.info("sleeping for %s seconds", max(data))
        time.sleep(max(data))
        return data


if __name__ == "__main__":
    server = Server()
    server.append_worker(Preprocess, num=2)
    server.append_worker(Inference, max_batch_size=32)
    server.run()
