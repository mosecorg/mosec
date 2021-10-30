import json
import multiprocessing as mp
import os
import random
import shutil
import socket
import struct
import tempfile
import time
from contextlib import ContextDecorator
from os.path import join

import msgpack  # type: ignore
import pytest

from mosec.coordinator import PROTOCOL_TIMEOUT, STAGE_EGRESS, STAGE_INGRESS, Coordinator
from mosec.protocol import Protocol, _recv_all
from mosec.worker import Worker

from .mock_logger import MockLogger
from .utils import imitate_controller_send

socket_prefix = join(tempfile.gettempdir(), "test-mosec")
stage = STAGE_INGRESS + STAGE_EGRESS


def clean_dir():
    if os.path.exists(socket_prefix):
        shutil.rmtree(socket_prefix)


class CleanDirContext(ContextDecorator):
    def __enter__(self):
        clean_dir()
        return self

    def __exit__(self, *exc):
        clean_dir()
        return False


class EchoWorkerJSON(Worker):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def forward(self, data):
        return data


class EchoWorkerMSGPACK(EchoWorkerJSON):
    @staticmethod
    def deserialize(data):
        return msgpack.unpackb(data)

    @staticmethod
    def serialize(data):
        return msgpack.packb(data)


@pytest.fixture
def base_test_config():
    return {
        "max_batch_size": 1,
        "stage_id": 1,
        "worker_id": 1,
        "c_ctx": "spawn",
    }


def make_coordinator_process(w_cls, c_ctx, shutdown, shutdown_notify, config):
    return mp.get_context(c_ctx).Process(
        target=Coordinator,
        args=(
            w_cls,
            config["max_batch_size"],
            stage,
            shutdown,
            shutdown_notify,
            socket_prefix,
            config["stage_id"],
            config["worker_id"],
        ),
        daemon=True,
    )


def test_socket_file_not_found(mocker, base_test_config):
    mocker.patch("mosec.coordinator.logger", MockLogger())
    mocker.patch("mosec.coordinator.CONN_MAX_RETRY", 5)
    mocker.patch("mosec.coordinator.CONN_CHECK_INTERVAL", 0.1)

    c_ctx = base_test_config.pop("c_ctx")
    shutdown = mp.get_context(c_ctx).Event()
    shutdown_notify = mp.get_context(c_ctx).Event()

    with CleanDirContext():
        with pytest.raises(RuntimeError, match=r".*cannot find.*"):
            _ = Coordinator(
                EchoWorkerJSON,
                stage=stage,
                shutdown=shutdown,
                shutdown_notify=shutdown_notify,
                socket_prefix=socket_prefix,
                **base_test_config,
            )


def test_incorrect_socket_file(mocker, base_test_config):
    mocker.patch("mosec.coordinator.logger", MockLogger())
    mocker.patch("mosec.coordinator.CONN_MAX_RETRY", 5)
    mocker.patch("mosec.coordinator.CONN_CHECK_INTERVAL", 0.1)

    sock_addr = join(socket_prefix, f"ipc_{base_test_config.get('stage_id')}.socket")
    c_ctx = base_test_config.pop("c_ctx")
    shutdown = mp.get_context(c_ctx).Event()
    shutdown_notify = mp.get_context(c_ctx).Event()

    with CleanDirContext():
        os.makedirs(socket_prefix, exist_ok=False)
        # create non-socket file
        open(sock_addr, "w").close()

        with pytest.raises(RuntimeError, match=r".*connection error*"):
            _ = Coordinator(
                EchoWorkerJSON,
                stage=stage,
                shutdown=shutdown,
                shutdown_notify=shutdown_notify,
                socket_prefix=socket_prefix,
                **base_test_config,
            )

    with CleanDirContext():
        os.makedirs(socket_prefix, exist_ok=False)
        # bind to a socket file to which no server is listening
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(sock_addr)

        with pytest.raises(RuntimeError, match=r".*Connection refused.*"):
            _ = Coordinator(
                EchoWorkerJSON,
                stage=stage,
                shutdown=shutdown,
                shutdown_notify=shutdown_notify,
                socket_prefix=socket_prefix,
                **base_test_config,
            )


@pytest.mark.parametrize(
    "test_data,worker,deserializer",
    [
        (
            [json.dumps({"rid": "147982364", "data": "im_b64_str"}).encode()]
            * random.randint(1, 20),
            EchoWorkerJSON,
            json.loads,
        ),
        (
            [
                json.dumps({"rid": "147982364", "data": "im_b64_str"}).encode(),
                json.dumps({"rid": "147982831", "data": "another_im_b64_str"}).encode(),
            ],
            EchoWorkerJSON,
            json.loads,
        ),
        (
            [
                msgpack.packb({"rid": "147982364", "data": b"im_bytes"}),
                msgpack.packb({"rid": "147982831", "data": b"another_im_bytes"}),
            ],
            EchoWorkerMSGPACK,
            msgpack.unpackb,
        ),
    ],
)
def test_echo(mocker, base_test_config, test_data, worker, deserializer):
    mocker.patch("mosec.coordinator.logger", MockLogger())
    c_ctx = base_test_config.pop("c_ctx")
    base_test_config["max_batch_size"] = 8

    sock_addr = join(socket_prefix, f"ipc_{base_test_config.get('stage_id')}.socket")
    shutdown = mp.get_context(c_ctx).Event()
    shutdown_notify = mp.get_context(c_ctx).Event()

    with CleanDirContext():
        os.makedirs(socket_prefix, exist_ok=False)

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(sock_addr)
        sock.listen()

        coordinator_process = make_coordinator_process(
            worker, c_ctx, shutdown, shutdown_notify, base_test_config
        )
        coordinator_process.start()

        try:
            conn, _ = sock.accept()  # blocking

            # 1) prepare task datum
            sent_ids, sent_payloads = imitate_controller_send(conn, test_data)

            # 2) get back task results
            got_flag = struct.unpack("!H", conn.recv(2))[0]
            got_batch_size = struct.unpack("!H", conn.recv(2))[0]
            got_ids = []
            got_payloads = []
            while got_batch_size > 0:
                got_batch_size -= 1
                got_ids.append(conn.recv(4))
                got_length = struct.unpack("!I", conn.recv(4))[0]
                got_payloads.append(_recv_all(conn, got_length))
            assert got_flag == Protocol.FLAG_OK
            assert got_ids == sent_ids
            assert all(
                [
                    deserializer(x) == deserializer(y)
                    for x, y in zip(got_payloads, sent_payloads)
                ]
            )
            shutdown.set()
            # wait for socket timeout, make the client not read closed socket
            time.sleep(PROTOCOL_TIMEOUT)
        except Exception as e:
            shutdown.set()
            raise e
