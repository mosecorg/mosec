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

"""Example: Using Redis store with mosec plugin RedisShmWrapper.

We start a subprocess for the redis-server, and pass the url
to the redis client which serves as the shm wrapper.
We also register the redis-server process as a daemon, so
that when it exits the service is able to gracefully shutdown
and restarted by the orchestrator.
"""

import subprocess
from functools import partial

from mosec import Server, ValidationError, Worker
from mosec.plugins import RedisShmWrapper


class DataProducer(Worker):
    """Sample Data Producer."""

    def forward(self, data: dict) -> bytes:
        try:
            data_bytes = b"a" * int(data["size"])
        except KeyError as err:
            raise ValidationError(err) from err
        return data_bytes


class DataConsumer(Worker):
    """Sample Data Consumer."""

    def forward(self, data: bytes) -> dict:
        return {"ipc test data length": len(data)}


if __name__ == "__main__":
    with subprocess.Popen(["redis-server"]) as p:  # start redis server
        server = Server(
            ipc_wrapper=partial(  # defer the wrapper init to worker processes
                RedisShmWrapper,
                url="redis://localhost:6379/0",
            )
        )
        server.register_daemon("redis-server", p)
        server.append_worker(DataProducer, num=2)
        server.append_worker(DataConsumer, num=2)
        server.run()