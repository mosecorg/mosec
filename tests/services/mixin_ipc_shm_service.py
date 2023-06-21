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

import subprocess
import sys
from typing import List

import numpy as np
from pyarrow import plasma  # type: ignore

from mosec import Server, Worker
from mosec.errors import ValidationError
from mosec.mixin import PlasmaShmIPCMixin, RedisShmIPCMixin


class PlasmaRandomService(PlasmaShmIPCMixin, Worker):
    def forward(self, data: List[dict]) -> List[dict]:
        try:
            result = [{"x": np.random.rand(int(req["size"]))} for req in data]
        except KeyError as err:
            raise ValidationError(err)
        return result


class PlasmaDummyPostprocess(PlasmaShmIPCMixin, Worker):
    """This dummy stage is added to test the shm IPC"""

    def forward(self, data: dict) -> dict:
        assert isinstance(data.get("x"), np.ndarray), f"wrong data type: {data}"
        data["x"] = data["x"].tolist()
        return data


class RedisRandomService(RedisShmIPCMixin, Worker):
    def forward(self, data: List[dict]) -> List[dict]:
        try:
            result = [{"x": np.random.rand(int(req["size"]))} for req in data]
        except KeyError as err:
            raise ValidationError(err)
        return result


class RedisDummyPostprocess(RedisShmIPCMixin, Worker):
    """This dummy stage is added to test the shm IPC"""

    def forward(self, data: dict) -> dict:
        assert isinstance(data.get("x"), np.ndarray), f"wrong data type: {data}"
        data["x"] = data["x"].tolist()
        return data


def start_redis_shm_mosec():
    with subprocess.Popen(["redis-server"]) as p:  # start the redis server
        # configure the plasma service path
        RedisShmIPCMixin.set_redis_url("redis://localhost:6379/0")

        server = Server()
        # register this process to be monitored
        server.register_daemon("redis_server", p)
        server.append_worker(RedisRandomService, max_batch_size=8)
        server.append_worker(RedisDummyPostprocess, num=2)
        server.run()


def start_plasma_shm_mosec():
    # initialize a 20Mb object store as shared memory
    with plasma.start_plasma_store(plasma_store_memory=20 * 1000 * 1000) as (
        shm_path,
        shm_process,
    ):
        # configure the plasma shm path
        PlasmaShmIPCMixin.set_plasma_path(shm_path)

        server = Server()
        server.register_daemon("plasma_server", shm_process)
        server.append_worker(PlasmaRandomService, max_batch_size=8)
        server.append_worker(PlasmaDummyPostprocess, num=2)
        server.run()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Please specify a shm to run: plasma or redis")
        exit(1)

    shm = sys.argv[1]
    if shm == "plasma":
        start_plasma_shm_mosec()
    elif shm == "redis":
        start_redis_shm_mosec()
