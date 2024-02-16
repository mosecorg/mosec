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

"""Test worker timeout configuration."""

import os
import time
from typing import Any

from mosec import Server, Worker, get_logger

logger = get_logger()


class SleepyInference(Worker):
    """Sample Class."""

    def forward(self, data: Any) -> Any:
        sleep_duration = float(os.environ["SLEEP_DURATION"])
        logger.info("sleep_duration %s", sleep_duration)
        time.sleep(sleep_duration)
        return data


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()

    parser.add_argument("--sleep-duration", type=float, help="worker sleep duration")
    parser.add_argument("--worker-timeout", type=int, help="worker timeout")
    parser.add_argument("--port", type=int, help="port")

    args = parser.parse_args()

    sleep_duration = args.sleep_duration
    worker_timeout = args.worker_timeout
    server = Server()
    server.append_worker(
        SleepyInference,
        timeout=worker_timeout,
        env=[{"SLEEP_DURATION": str(sleep_duration)}],
    )
    server.run()
