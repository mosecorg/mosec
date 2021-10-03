import random
import subprocess
import time
from threading import Thread

import httpx  # type: ignore
import pytest

import mosec

TEST_PORT = "8090"
URI = f"http://localhost:{TEST_PORT}"


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


def test_square_service(mosec_service):
    resp = httpx.get(URI)
    assert resp.status_code == 200
    assert f"mosec/{mosec.__version__}" == resp.headers["server"]

    resp = httpx.get(f"{URI}/metrics")
    assert resp.status_code == 200

    resp = httpx.post(f"{URI}/inference", json={"msg": 2})
    assert resp.status_code == 422

    resp = httpx.post(f"{URI}/inference", data=b"bad-binary-request")
    assert resp.status_code == 422

    validate_square_service(2)


def test_square_service_mp(mosec_service):
    threads = []
    for _ in range(20):
        x = Thread(target=validate_square_service, args=(random.randint(-500, 500),))
        x.start()
        threads.append(x)
    for t in threads:
        t.join()


def validate_square_service(x):
    resp = httpx.post(f"{URI}/inference", json={"x": x})
    assert resp.json()["x"] == x ** 2
