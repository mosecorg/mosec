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
from pyarrow import plasma  # type: ignore

from mosec import Server, Worker
from mosec.middleware import IPCMiddleware, Middleware
from mosec.plugins.plasma_shm import PlasmaShmWrapper


class Preprocess(Worker):
    def forward(self, data: Dict[str, str]) -> np.ndarray:
        num = int(data.get("num", 10))
        arr = np.ones(num) * (1 / num)
        return arr


class Middle(Worker):
    def forward(self, data: np.ndarray) -> np.ndarray:
        return data + 1


class Inference(Worker):
    def forward(self, data: np.ndarray) -> np.ndarray:
        return data.sum()


class DataLogger(Middleware):
    def preprocess(self, data):
        print(f"preprocess {data}")
        return data

    def postprocess(self, data):
        print(f"postprocess {data}")
        return data


class Timer(Middleware):
    prefix = ""

    def __init__(self) -> None:
        self.timer = time.time()

    def preprocess(self, data: Any) -> Any:
        self.timer = time.time()
        return data

    def postprocess(self, data: Any) -> Any:
        seconds = time.time() - self.timer
        print(f"{self.prefix} cost : {seconds}s")
        return data


class FullTimer(Timer):
    prefix = "full"


class ForwardTimer(Timer):
    prefix = "forward"


class Incrementer(Middleware):
    def preprocess(self, data: List[np.ndarray]) -> List[np.ndarray]:
        return [d + 1 for d in data]


class PlasmaStore(Middleware):
    def __init__(self, shm_path: str) -> None:
        self.plasma = PlasmaShmWrapper(shm_path)

    def preprocess(self, data: List[Any]) -> List[Any]:
        return self.plasma.get(data)

    def postprocess(self, data: List[Any]) -> List[Any]:
        return self.plasma.put(data)


class PlasmaStoreIngress(PlasmaStore):
    def preprocess(self, data: List[Any]) -> List[Any]:
        return data


class PlasmaStoreEgress(PlasmaStore):
    def postprocess(self, data: List[Any]) -> List[Any]:
        return data


class EasyPlasmaStore(IPCMiddleware):
    def __init__(self, shm_path: str) -> None:
        self.plasma = PlasmaShmWrapper(shm_path)

    def put(self, data):
        return self.plasma.put(data)

    def get(self, ids):
        return self.plasma.get(ids)


if __name__ == "__main__":
    with plasma.start_plasma_store(plasma_store_memory=200 * 1000 * 1000) as (
        shm_path,
        shm_process,
    ):
        server = Server()
        server.register_daemon("plasma_server", shm_process)

        # IngressStore = partial(PlasmaStoreIngress, shm_path)
        # MiddleStore = partial(PlasmaStore, shm_path)
        # EgressStore = partial(PlasmaStoreEgress, shm_path)

        # server.append_worker(
        #     Preprocess,
        #     middlewares=[FullTimer, IngressStore, ForwardTimer],
        # )
        # server.append_worker(
        #     Middle,
        #     middlewares=[FullTimer, MiddleStore, ForwardTimer],
        # )
        # server.append_worker(
        #     Inference,
        #     middlewares=[FullTimer, EgressStore, Incrementer, ForwardTimer],
        # )

        SimpleStore = partial(EasyPlasmaStore, shm_path)

        server.append_worker(
            Preprocess,
            middlewares=[FullTimer, SimpleStore, ForwardTimer],
        )
        server.append_worker(
            Middle,
            middlewares=[FullTimer, SimpleStore, ForwardTimer],
        )
        server.append_worker(
            Inference,
            middlewares=[FullTimer, SimpleStore, Incrementer, ForwardTimer],
        )
        server.run()
