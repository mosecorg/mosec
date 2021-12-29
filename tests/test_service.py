import random
import re
import subprocess
import time
from threading import Thread

import httpx  # type: ignore
import pytest

import mosec

TEST_PORT = "8090"


def get_uri(port):
    return f"http://localhost:{port}"


@pytest.fixture(scope="module")
def http_client():
    client = httpx.Client()
    yield client
    client.close()


def start_service(service_name, port):
    return subprocess.Popen(
        ["python", f"tests/{service_name}.py", "--port", port],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


@pytest.fixture(scope="session")
def mosec_service(request):
    name, port = request.param
    service = start_service(name, port)
    time.sleep(2)  # wait for service to start
    assert not service.poll(), service.stdout.read().decode("utf-8")
    yield port
    service.terminate()


@pytest.mark.parametrize(
    "mosec_service, http_client",
    [
        pytest.param(("square_service", "8090"), "", id="normal"),
        pytest.param(
            ("square_service_shm", "8091"),
            "",
            marks=pytest.mark.arrow,
            id="shm_arrow",
        ),
    ],
    indirect=["mosec_service", "http_client"],
)
def test_square_service(mosec_service, http_client):
    uri = get_uri(mosec_service)
    resp = http_client.get(uri)
    assert resp.status_code == 200
    assert f"mosec/{mosec.__version__}" == resp.headers["server"]

    resp = http_client.get(f"{uri}/metrics")
    assert resp.status_code == 200

    resp = http_client.post(f"{uri}/inference", json={"msg": 2})
    assert resp.status_code == 422

    resp = http_client.post(f"{uri}/inference", content=b"bad-binary-request")
    assert resp.status_code == 400

    validate_square_service(http_client, uri, 2)


@pytest.mark.parametrize(
    "mosec_service, http_client",
    [
        pytest.param(("square_service", "8090"), "", id="normal"),
        pytest.param(
            ("square_service_shm", "8091"),
            "",
            marks=pytest.mark.arrow,
            id="shm_arrow",
        ),
    ],
    indirect=["mosec_service", "http_client"],
)
def test_square_service_mp(mosec_service, http_client):
    uri = get_uri(mosec_service)
    threads = []
    for _ in range(20):
        t = Thread(
            target=validate_square_service,
            args=(http_client, uri, random.randint(-500, 500)),
        )
        t.start()
        threads.append(t)
    for t in threads:
        t.join()
    assert_batch_larger_than_one(http_client, uri)
    assert_empty_queue(http_client, uri)


def validate_square_service(http_client, uri, x):
    resp = http_client.post(f"{uri}/inference", json={"x": x})
    assert resp.json()["x"] == x ** 2


def assert_batch_larger_than_one(http_client, uri):
    metrics = http_client.get(f"{uri}/metrics").content.decode()
    bs = re.findall(r"batch_size_bucket.+", metrics)
    get_bs_int = lambda x: int(x.split(" ")[-1])  # noqa
    assert get_bs_int(bs[-1]) > get_bs_int(bs[0])


def assert_empty_queue(http_client, uri):
    metrics = http_client.get(f"{uri}/metrics").content.decode()
    remain = re.findall(r"mosec_service_remaining_task \d+", metrics)[0]
    assert int(remain.split(" ")[-1]) == 0
