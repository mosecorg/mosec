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
import shlex
import subprocess
import time

import httpx
import pytest

from tests.utils import wait_for_port_open

TIMEOUT_SERVICE_PORT = 8000


@pytest.fixture
def example_server(request):
    name = request.param
    filepath = os.path.join("examples", name)
    service = subprocess.Popen(
        shlex.split(f"python -u {filepath}.py --port {TIMEOUT_SERVICE_PORT}")
    )
    assert wait_for_port_open(
        port=TIMEOUT_SERVICE_PORT, timeout=5
    ), "service failed to start"
    yield name
    service.terminate()
    time.sleep(2)  # wait for service to stop


@pytest.mark.parametrize(
    "example_server,example_client",
    [
        pytest.param(
            "type_validation/server",
            "type_validation/client",
            id="type_validation",
        ),
        pytest.param(
            "echo",
            "client",
            id="echo",
        ),
        pytest.param(
            "redis_shm_ipc",
            "client",
            id="redis_shm_ipc",
        ),
        pytest.param(
            "plasma_shm_ipc",
            "client",
            id="plasma_shm_ipc",
        ),
        pytest.param(
            "jax_single_layer",
            "jax_single_layer_cli",
            id="jax_single_layer",
        ),
    ],
    indirect=["example_server"],
)
def test_forward_timeout(example_server, example_client: str):
    filepath = os.path.join("examples", example_client)
    service = subprocess.Popen(shlex.split(f"python -u {filepath}.py {example_server}"))
    stdout, stderr = service.communicate()
    code = service.returncode
    assert code == 0, (code, stdout, stderr)
