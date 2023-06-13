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

import random
import re
import shlex
import subprocess
import time
from http import HTTPStatus
from threading import Thread

import httpx
import msgpack  # type: ignore
import pytest
from httpx_sse import connect_sse

from mosec.server import GUARD_CHECK_INTERVAL
from tests.utils import wait_for_port_open

TEST_PORT = 5000


@pytest.fixture
def http_client():
    with httpx.Client(base_url=f"http://127.0.0.1:{TEST_PORT}") as client:
        yield client


@pytest.fixture(scope="session")
def mosec_service(request):
    params = request.param.split(" ")
    name = params[0]
    args = " ".join(params[1:])
    service = subprocess.Popen(
        shlex.split(f"python -u tests/{name}.py {args} --port {TEST_PORT}"),
    )
    assert wait_for_port_open(port=TEST_PORT), "service failed to start"
    yield service
    service.terminate()
    time.sleep(2)  # wait for service to stop


@pytest.mark.parametrize(
    "mosec_service, http_client",
    [
        pytest.param("square_service", "", id="basic"),
    ],
    indirect=["mosec_service", "http_client"],
)
def test_square_service(mosec_service, http_client):
    resp = http_client.get("/")
    assert resp.status_code == HTTPStatus.OK
    # only check the prefix since the version from setuptools_scm may not be the
    # correct one used in `Cargo.toml`
    assert resp.headers["server"].startswith("mosec/"), f"{resp.headers['server']}"

    resp = http_client.get("/metrics")
    assert resp.status_code == HTTPStatus.OK

    resp = http_client.post("/v1/inference", json={"msg": 2})
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert resp.text == "request validation error: 'x'"

    resp = http_client.post("/v1/inference", content=b"bad-binary-request")
    assert resp.status_code == HTTPStatus.BAD_REQUEST

    validate_square_service(http_client, 2)


@pytest.mark.parametrize(
    "mosec_service, http_client",
    [
        pytest.param(
            "mixin_ipc_shm_service plasma", "", id="shm_plasma", marks=pytest.mark.shm
        ),
        pytest.param(
            "mixin_ipc_shm_service redis", "", id="shm_redis", marks=pytest.mark.shm
        ),
    ],
    indirect=["mosec_service", "http_client"],
)
def test_mixin_ipc_shm_service(mosec_service, http_client):
    resp = http_client.post("/inference", json={"size": 8})
    assert resp.status_code == HTTPStatus.OK, resp
    assert len(resp.json().get("x")) == 8
    assert resp.headers["content-type"] == "application/json"


@pytest.mark.parametrize(
    "mosec_service, http_client",
    [
        pytest.param("mixin_numbin_service", "", id="numbin"),
    ],
    indirect=["mosec_service", "http_client"],
)
def test_mixin_ipc_service(mosec_service, http_client):
    resp = http_client.post("/inference", json={"num": 8})
    assert resp.status_code == HTTPStatus.OK, resp
    assert resp.json() == "equal"
    assert resp.headers["content-type"] == "application/json"


@pytest.mark.parametrize(
    "mosec_service, http_client",
    [
        pytest.param("mixin_typed_service", "", id="typed"),
    ],
    indirect=["mosec_service", "http_client"],
)
def test_mixin_typed_service(mosec_service, http_client):
    resp = http_client.post(
        "/inference",
        content=msgpack.packb(
            {
                "media": "text",
                "binary": b"hello mosec",
            }
        ),
    )
    assert resp.status_code == HTTPStatus.OK, resp
    assert resp.headers["content-type"] == "application/msgpack"
    assert msgpack.unpackb(resp.content) == 11

    # sleep long enough to make sure all the processes have been checked
    # ref to https://github.com/mosecorg/mosec/pull/379#issuecomment-1578304988
    time.sleep(GUARD_CHECK_INTERVAL + 1)

    resp = http_client.post("/inference", content=msgpack.packb({"media": "none"}))
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, resp


@pytest.mark.parametrize(
    "mosec_service, http_client",
    [
        pytest.param("sse_service", "", id="sse"),
    ],
    indirect=["mosec_service", "http_client"],
)
def test_sse_service(mosec_service, http_client):
    round = 0
    with connect_sse(
        http_client, "POST", "/sse_inference", json={"text": "mosec"}
    ) as event_source:
        for sse in event_source.iter_sse():
            round += 1
            assert sse.event == "message"
            assert sse.data == "mosec"
    assert round == 5

    round = 0
    with connect_sse(
        http_client, "POST", "/sse_inference", json={"bad": "req"}
    ) as event_source:
        for sse in event_source.iter_sse():
            round += 1
            assert sse.event == "error"
            assert sse.data == (
                "SSE inference error: 422: Unprocessable Content: "
                "request validation error: text is required"
            )
    assert round == 1


@pytest.mark.parametrize(
    "mosec_service, http_client",
    [
        pytest.param("square_service", "", id="basic"),
    ],
    indirect=["mosec_service", "http_client"],
)
def test_square_service_mp(mosec_service, http_client):
    threads = []
    for _ in range(20):
        t = Thread(
            target=validate_square_service,
            args=(http_client, random.randint(-500, 500)),
        )
        t.start()
        threads.append(t)
    for t in threads:
        t.join()
    assert_batch_larger_than_one(http_client)
    assert_empty_queue(http_client)


def validate_square_service(http_client, x):
    resp = http_client.post("/v1/inference", json={"x": x})
    assert resp.status_code == HTTPStatus.OK
    assert resp.json()["x"] == x**2


def assert_batch_larger_than_one(http_client):
    metrics = http_client.get("/metrics").content.decode()
    bs = re.findall(r"batch_size_bucket.+", metrics)
    get_bs_int = lambda x: int(x.split(" ")[-1])  # noqa
    assert get_bs_int(bs[-1]) > get_bs_int(bs[0])


def assert_empty_queue(http_client):
    metrics = http_client.get("/metrics").content.decode()
    remain = re.findall(r"mosec_service_remaining_task \d+", metrics)[0]
    assert int(remain.split(" ")[-1]) == 0
