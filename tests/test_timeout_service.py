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


import random
import shlex
import socket
import subprocess
import time
from typing import Any, Type

import httpx
import pytest

from mosec import Worker


def wait_for_port_open(host: str, port: int, timeout: int):
    start_time = time.monotonic()
    while time.monotonic() - start_time < timeout:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.connect((host, port))
            sock.shutdown(socket.SHUT_RDWR)
            return True
        except (ConnectionRefusedError, OSError):
            pass
        finally:
            sock.close()
        time.sleep(0.1)
    return False


def wait_for_port_free(host: str, port: int, timeout: int):
    start_time = time.monotonic()
    while time.monotonic() - start_time < timeout:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.connect((host, port))
            sock.shutdown(socket.SHUT_RDWR)
        except ConnectionRefusedError:
            return True
        finally:
            sock.close()
        time.sleep(0.1)
    return False


@pytest.mark.parametrize(
    "worker_cls,server_timeout,status_code,port",
    [
        ("SleepyInference1", 1, 408, 8000),
        ("SleepyInference1", 2, 200, 8001),
        ("SleepyInference2", 2, 408, 8002),
        ("SleepyInference4", 5, 408, 8003),
    ],
)
def test_forward_timeout(
    worker_cls: Type[Worker], server_timeout: int, status_code: int, port: int
):
    p = subprocess.Popen(
        shlex.split(
            f"python -u tests/timeout_service.py --worker_cls {worker_cls} --server_timeout {server_timeout} --status_code {status_code} --port {port}"
        )
    )
    assert (
        wait_for_port_open("127.0.0.1", port, 30) is True
    ), "service failed to start in 30s"
    input_data = [random.randint(-99, 99)]
    response = httpx.post(
        f"http://localhost:{port}/inference",
        json={"array": input_data},
    )
    assert response.status_code == status_code
    p.terminate()
    assert (
        wait_for_port_free("127.0.0.1", port, 30) is True
    ), "service failed to terminate in 30s"


if __name__ == "__main__":
    params = [
        ("SleepyInference1", 1, 408, 8000),
        ("SleepyInference1", 2, 200, 8001),
        ("SleepyInference2", 2, 408, 8002),
        ("SleepyInference4", 5, 408, 8003),
    ]
    for param in params:
        test_forward_timeout(*param)
