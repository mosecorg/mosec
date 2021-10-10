import random
import re
import subprocess
import time
from threading import Thread

import httpx  # type: ignore
import pytest

import mosec

TEST_PORT = "8090"
URI = f"http://localhost:{TEST_PORT}"


@pytest.fixture(scope="module")
def http_client():
    client = httpx.Client()
    yield client
    client.close()


@pytest.fixture(scope="session")
def mosec_service():
    service = subprocess.Popen(
        ["python", "tests/square_service.py", "--port", TEST_PORT],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    time.sleep(2)  # wait for service to start
    assert not service.poll(), service.stdout.read().decode("utf-8")
    yield service
    service.terminate()


def test_square_service(mosec_service, http_client):
    resp = http_client.get(URI)
    assert resp.status_code == 200
    assert f"mosec/{mosec.__version__}" == resp.headers["server"]

    resp = http_client.get(f"{URI}/metrics")
    assert resp.status_code == 200

    resp = http_client.post(f"{URI}/inference", json={"msg": 2})
    assert resp.status_code == 422

    resp = http_client.post(f"{URI}/inference", content=b"bad-binary-request")
    assert resp.status_code == 400

    validate_square_service(http_client, 2)


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


def validate_square_service(http_client, x):
    resp = http_client.post(f"{URI}/inference", json={"x": x})
    assert resp.json()["x"] == x ** 2


def assert_batch_larger_than_one(http_client):
    metrics = http_client.get(f"{URI}/metrics").content.decode()
    bs = re.findall(r"batch_size_bucket.+", metrics)
    get_bs_int = lambda x: int(x.split(" ")[-1])  # noqa
    assert get_bs_int(bs[-1]) > get_bs_int(bs[0])
