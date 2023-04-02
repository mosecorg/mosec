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


import multiprocessing
import random
import shlex
import socket
import subprocess
import time
from typing import Any, Type

import httpx
import pytest

from mosec import Server, Worker


class SleepyInference1(Worker):
    """Sample Class."""

    def forward(self, data: Any) -> Any:
        time.sleep(1.9)
        return data


class SleepyInference2(Worker):
    """Sample Class."""

    def forward(self, data: Any) -> Any:
        time.sleep(2)
        return data


class SleepyInference4(Worker):
    """Sample Class."""

    def forward(self, data: Any) -> Any:
        time.sleep(4)
        return data


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()

    # 添加参数
    parser.add_argument("--worker_cls", type=str, help="worker class name")
    parser.add_argument("--server_timeout", type=int, help="server timeout")
    parser.add_argument("--status_code", type=int, help="status code")
    parser.add_argument("--port", type=int, help="port")

    # 解析命令行参数
    args = parser.parse_args()

    # 获取参数值
    worker_cls = args.worker_cls
    server_timeout = args.server_timeout
    status_code = args.status_code

    if worker_cls == "SleepyInference1":
        worker_cls = SleepyInference1
    elif worker_cls == "SleepyInference2":
        worker_cls = SleepyInference2
    elif worker_cls == "SleepyInference4":
        worker_cls = SleepyInference4
    server = Server()
    server.append_worker(worker_cls, timeout=server_timeout)
    server.run()
