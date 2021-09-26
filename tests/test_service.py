import subprocess

import httpx
import pytest


@pytest.fixture(scope="session")
def mosec_service():
    service = subprocess.Popen(["python", "tests/square_service.py"])
    yield service
    service.terminate()


def test_square_service(mosec_service):
    pass
