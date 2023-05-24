# Copyright 2023 MOSEC Authors
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

"""Example: Using Plasma store with mosec mixin PlasmaShmIPCMixin.

We start a subprocess for the Redis server, and pass the url
to the redis client which serves as the shm mixin.
We also register the redis server process as a daemon, so
that when it exits the service is able to gracefully shut down
and be restarted by the orchestrator.
"""

import subprocess

from mosec import Server, ValidationError, Worker
from mosec.mixin import RedisShmIPCMixin


class DataProducer(RedisShmIPCMixin, Worker):
    """Sample Data Producer."""

    def forward(self, data: dict) -> bytes:
        try:
            data_bytes = b"a" * int(data["size"])
        except KeyError as err:
            raise ValidationError(err) from err
        return data_bytes


class DataConsumer(RedisShmIPCMixin, Worker):
    """Sample Data Consumer."""

    def forward(self, data: bytes) -> dict:
        return {"ipc test data length": len(data)}


if __name__ == "__main__":
    with subprocess.Popen(["redis-server"]) as p:  # start the redis server
        # configure the plasma service path
        RedisShmIPCMixin.set_redis_url("redis://localhost:6379/0")

        server = Server()
        # register this process to be monitored
        server.register_daemon("redis_server", p)
        server.append_worker(DataProducer, num=2)
        server.append_worker(DataConsumer, num=2)
        server.run()
