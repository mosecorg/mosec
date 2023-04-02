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

import os
import time
from typing import Any

from mosec import Server, Worker, get_logger

logger = get_logger()


class SleepyInference(Worker):
    """Sample Class."""

    def forward(self, data: Any) -> Any:
        worker_timeout = float(os.environ["worker_timeout"])
        logger.info(f"worker_timeout {worker_timeout}")
        time.sleep(worker_timeout)
        return data


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()

    parser.add_argument("--worker_timeout", type=float, help="worker timeout")
    parser.add_argument("--server_timeout", type=int, help="server timeout")
    parser.add_argument("--port", type=int, help="port")

    args = parser.parse_args()

    worker_timeout = args.worker_timeout
    server_timeout = args.server_timeout
    server = Server()
    server.append_worker(
        SleepyInference,
        timeout=server_timeout,
        env=[{"worker_timeout": str(worker_timeout)}],
    )
    server.run()
