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

"""End-to-end service tests."""

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
from tests.utils import wait_for_port_free, wait_for_port_open

# choose a special port to avoid conflict with local services
TEST_PORT = 5753


@pytest.fixture
def http_client():
    with httpx.Client(base_url=f"http://127.0.0.1:{TEST_PORT}") as client:
        yield client


@pytest.fixture
def http2_client():
    # force to use HTTP/2
    with httpx.Client(
        base_url=f"http://127.0.0.1:{TEST_PORT}", http1=False, http2=True
    ) as client:
        yield client


@pytest.fixture(scope="session")
def mosec_service(request):
    params = request.param.split(" ")
    name = params[0]
    args = " ".join(params[1:])
    service = subprocess.Popen(
        shlex.split(f"python -u tests/services/{name}.py {args} --port {TEST_PORT}"),
    )
    assert wait_for_port_open(port=TEST_PORT), "service failed to start"
    yield service
    service.terminate()
    assert wait_for_port_free(port=TEST_PORT), "service failed to stop"


@pytest.mark.parametrize(
    "mosec_service, http2_client",
    [
        pytest.param("square_service", "", id="HTTP/2"),
    ],
    indirect=["mosec_service", "http2_client"],
)
def test_http2_service(mosec_service, http2_client):
    resp = http2_client.get("/")
    assert resp.status_code == HTTPStatus.OK
    assert resp.http_version == "HTTP/2"


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

    resp = http_client.post("/inference", json={"msg": 2})
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert resp.text == "request validation error: 'x'"

    resp = http_client.post("/inference", content=b"bad-binary-request")
    assert resp.status_code == HTTPStatus.BAD_REQUEST

    validate_square_service(http_client, 2)


@pytest.mark.parametrize(
    "mosec_service,http_client,status_code",
    [
        pytest.param(
            "timeout_service --sleep-duration 1.5 --worker-timeout 1",
            None,
            HTTPStatus.REQUEST_TIMEOUT,
            id="worker-forward-trigger-worker-timeout",
        ),
        pytest.param(
            "timeout_service --sleep-duration 1.0 --worker-timeout 2",
            None,
            HTTPStatus.OK,
            id="normal-request-within-worker-timeout",
        ),
        pytest.param(
            "timeout_service --sleep-duration 3.5 --worker-timeout 4",
            None,
            HTTPStatus.REQUEST_TIMEOUT,
            id="worker-forward-trigger-service-timeout",
        ),
    ],
    indirect=["mosec_service", "http_client"],
)
def test_timeout_service(mosec_service, http_client, status_code):
    input_data = [random.randint(-99, 99)]
    resp = http_client.post("/inference", json={"array": input_data})
    assert resp.status_code == status_code, resp


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
    size = 8
    resp = http_client.post("/inference", json={"size": size})
    assert resp.status_code == HTTPStatus.OK, resp
    assert len(resp.json().get("x")) == size
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
    text = b"hello mosec"
    resp = http_client.post(
        "/inference",
        content=msgpack.packb(
            {
                "media": "text",
                "binary": text,
            }
        ),
    )
    assert resp.status_code == HTTPStatus.OK, resp
    assert resp.headers["content-type"] == "application/msgpack"
    assert msgpack.unpackb(resp.content) == len(text)

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
    epoch = 5
    count = 0
    with connect_sse(
        http_client, "POST", "/inference", json={"text": "mosec"}
    ) as event_source:
        for sse in event_source.iter_sse():
            count += 1
            assert sse.event == "message"
            assert sse.data == "mosec"
    assert count == epoch

    count = 0
    with connect_sse(
        http_client, "POST", "/inference", json={"bad": "req"}
    ) as event_source:
        for sse in event_source.iter_sse():
            count += 1
            assert sse.event == "error"
            assert sse.data == (
                "SSE inference error: 422: Unprocessable Content: "
                "request validation error: text is required"
            )
    assert count == 1


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
        thread = Thread(
            target=validate_square_service,
            args=(http_client, random.randint(-500, 500)),
        )
        thread.start()
        threads.append(thread)
    for thread in threads:
        thread.join()
    assert_batch_larger_than_one(http_client)
    assert_empty_queue(http_client)


def validate_square_service(http_client, num):
    resp = http_client.post("/inference", json={"x": num})
    assert resp.status_code == HTTPStatus.OK
    assert resp.json()["x"] == num**2


def assert_batch_larger_than_one(http_client):
    def get_batch_size_int(text):
        return int(text.split(" ")[-1])

    metrics = http_client.get("/metrics").content.decode()
    batch_size = re.findall(r"batch_size_bucket.+", metrics)
    assert get_batch_size_int(batch_size[-1]) > get_batch_size_int(batch_size[0])


def assert_empty_queue(http_client):
    metrics = http_client.get("/metrics").content.decode()
    remain = re.findall(r"mosec_service_remaining_task \d+", metrics)[0]
    assert int(remain.split(" ")[-1]) == 0


@pytest.mark.parametrize(
    "mosec_service, http_client, args",
    [
        pytest.param(
            "openapi_service TypedPreprocess/TypedInference",
            "",
            "TypedPreprocess/TypedInference",
            id="TypedPreprocess/TypedInference",
        ),
        pytest.param(
            "openapi_service UntypedPreprocess/TypedInference",
            "",
            "UntypedPreprocess/TypedInference",
            id="UntypedPreprocess/TypedInference",
        ),
        pytest.param(
            "openapi_service TypedPreprocess/UntypedInference",
            "",
            "TypedPreprocess/UntypedInference",
            id="TypedPreprocess/UntypedInference",
        ),
        pytest.param(
            "openapi_service UntypedPreprocess/UntypedInference",
            "",
            "UntypedPreprocess/UntypedInference",
            id="UntypedPreprocess/UntypedInference",
        ),
    ],
    indirect=["mosec_service", "http_client"],
)
def test_openapi_service(mosec_service, http_client, args):
    spec = http_client.get("/openapi/metadata.json").json()
    input_cls, return_cls = args.split("/")
    path_item = spec["paths"]["/v1/inference"]["post"]

    if input_cls == "TypedPreprocess":
        want = {
            "application/msgpack": {"schema": {"$ref": "#/components/schemas/Request"}}
        }
        assert path_item["requestBody"]["content"] == want
        assert "Request" in spec["components"]["schemas"]
    else:
        assert "requestBody" not in path_item

    if return_cls == "TypedInference":
        want = {"application/msgpack": {"schema": {"type": "integer"}}}
        assert path_item["responses"]["200"]["content"] == want
    else:
        assert "content" not in path_item["responses"]["200"]


@pytest.mark.parametrize(
    "mosec_service, http_client",
    [
        pytest.param("multi_route_service", "", id="multi-route"),
    ],
    indirect=["mosec_service", "http_client"],
)
def test_multi_route_service(mosec_service, http_client):
    data = b"mosec"
    req = {
        "name": "mosec-test",
        "bin": data,
    }

    # test /inference
    resp = http_client.post("/inference", content=data)
    assert resp.status_code == HTTPStatus.OK, resp
    assert resp.headers["content-type"] == "application/json"
    assert resp.json() == {"length": len(data)}

    # test /v1/inference
    resp = http_client.post("/v1/inference", content=msgpack.packb(req))
    assert resp.status_code == HTTPStatus.OK, resp
    assert resp.headers["content-type"] == "application/msgpack"
    assert msgpack.unpackb(resp.content) == {"length": len(data)}
