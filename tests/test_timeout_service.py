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
import subprocess
import time
from http import HTTPStatus

import httpx
import pytest

from tests.utils import wait_for_port_open

TIMEOUT_SERVICE_PORT = 5001


@pytest.fixture
def timeout_service(request):
    sleep_duration, worker_timeout = request.param
    service = subprocess.Popen(
        shlex.split(
            f"python -u tests/timeout_service.py --sleep_duration {sleep_duration} "
            f"--worker_timeout {worker_timeout} --port {TIMEOUT_SERVICE_PORT}"
        )
    )
    assert wait_for_port_open(
        port=TIMEOUT_SERVICE_PORT, timeout=5
    ), "service failed to start"
    yield service
    service.terminate()
    time.sleep(2)  # wait for service to stop


@pytest.mark.parametrize(
    "timeout_service,status_code",
    [
        pytest.param(
            (1.5, 1),
            HTTPStatus.REQUEST_TIMEOUT,
            id="worker-forward-trigger-worker-timeout",
        ),
        pytest.param(
            (1.0, 2),
            HTTPStatus.OK,
            id="normal-request-within-worker-timeout",
        ),
        pytest.param(
            (3.5, 4),
            HTTPStatus.REQUEST_TIMEOUT,
            id="worker-forward-trigger-service-timeout",
        ),
    ],
    indirect=["timeout_service"],
)
def test_forward_timeout(timeout_service, status_code: int):
    input_data = [random.randint(-99, 99)]
    response = httpx.post(
        f"http://127.0.0.1:{TIMEOUT_SERVICE_PORT}/inference",
        json={"array": input_data},
    )
    assert response.status_code == status_code, response
