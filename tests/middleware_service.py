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

import time
from functools import partial
from typing import Any, Dict, List

import numpy as np

from mosec import Server, Worker
from mosec.middleware import Middleware


class Preprocess(Worker):
    def forward(self, data: Dict[str, str]) -> np.ndarray:
        num = int(data.get("num", 10))
        arr = np.ones(num) * (1 / num)
        return arr


class Inference(Worker):
    def forward(self, data: np.ndarray) -> List[str]:
        res = data.sum()
        return res


class DataLogger(Middleware):
    def preprocess(self, data):
        print(f"preprocess {data}")
        return data

    def postprocess(self, data):
        print(f"postprocess {data}")
        return data


class Timer(Middleware):
    def __init__(self, prefix="", stage="") -> None:
        self.prefix = prefix
        self.stage = stage
        self.timer = time.time()

    def preprocess(self, data: Any) -> Any:
        self.timer = time.time()
        return data

    def postprocess(self, data: Any) -> Any:
        seconds = time.time() - self.timer
        print(f"{self.stage}-{self.prefix} cost : {seconds}s")
        return data


class Incrementer(Middleware):
    def preprocess(self, data: List[np.ndarray]) -> List[np.ndarray]:
        for d in data:
            d += 1
        return data


if __name__ == "__main__":
    server = Server()
    full_timer = partial(Timer, "full")
    forward_timer = partial(Timer, "forward")
    server.append_worker(
        Preprocess,
        timeout=100,
        middlewares=[
            partial(full_timer, "Preprocess"),
            DataLogger,
            partial(forward_timer, "Preprocess"),
        ],
    )
    server.append_worker(
        Inference,
        timeout=100,
        middlewares=[
            partial(full_timer, "Inference"),
            Incrementer,
            partial(forward_timer, "Inference"),
        ],
    )
    server.run()
