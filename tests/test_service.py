import subprocess
import time

import httpx  # type: ignore
import pytest

import mosec

TEST_PORT = "8090"


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
    URI = f"http://localhost:{TEST_PORT}"
    resp = httpx.get(URI)
    assert resp.status_code == 200
    assert f"mosec/{mosec.__version__}" == resp.headers["server"]

    resp = httpx.get(f"{URI}/metrics")
    assert resp.status_code == 200

    resp = httpx.post(f"{URI}/inference", json={"msg": 2})
    assert resp.status_code == 422

    resp = httpx.post(f"{URI}/inference", json={"x": 2})
    assert resp.json()["x"] == 4
