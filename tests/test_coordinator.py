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

"""Test Coordinator related logic."""

import json
import logging
import multiprocessing as mp
import os
import random
import shutil
import socket
import struct
import tempfile
import time
from contextlib import ContextDecorator
from multiprocessing.context import ForkContext, SpawnContext
from os.path import join
from typing import Union, cast

import pytest

from mosec.coordinator import PROTOCOL_TIMEOUT, Coordinator, State
from mosec.protocol import HTTPStatusCode, _recv_all
from mosec.worker import Worker
from tests.utils import imitate_controller_send

SOCKET_PREFIX = join(tempfile.gettempdir(), "test-mosec")


logger = logging.getLogger()
logger.addHandler(logging.StreamHandler())


def clean_dir():
    if os.path.exists(SOCKET_PREFIX):
        shutil.rmtree(SOCKET_PREFIX)


class CleanDirContext(ContextDecorator):
    def __enter__(self):
        clean_dir()
        return self

    def __exit__(self, *exc):
        clean_dir()
        return False


class EchoWorkerJSON(Worker):
    def forward(self, data):
        return data


@pytest.fixture
def base_test_config():
    return {
        "max_batch_size": 1,
        "stage_id": 1,
        "worker_id": 1,
        "c_ctx": "spawn",
        "timeout": 3,
    }


def test_coordinator_worker_property(mocker):
    mocker.patch("mosec.coordinator.CONN_MAX_RETRY", 5)
    mocker.patch("mosec.coordinator.CONN_CHECK_INTERVAL", 0.01)
    ctx = "spawn"
    max_batch_size = 16
    worker_id = 3
    coordinator = Coordinator(
        EchoWorkerJSON,
        max_batch_size=max_batch_size,
        shutdown=mp.get_context(ctx).Event(),
        shutdown_notify=mp.get_context(ctx).Event(),
        socket_prefix=SOCKET_PREFIX,
        stage_name=EchoWorkerJSON.__name__,
        worker_id=worker_id,
        timeout=3,
    )
    assert coordinator.worker.stage == EchoWorkerJSON.__name__
    assert coordinator.worker.worker_id == worker_id
    assert coordinator.worker.max_batch_size == max_batch_size


def make_coordinator(w_cls, shutdown, shutdown_notify, config):
    return Coordinator(
        w_cls,
        max_batch_size=config["max_batch_size"],
        shutdown=shutdown,
        shutdown_notify=shutdown_notify,
        socket_prefix=SOCKET_PREFIX,
        stage_name=f"{w_cls.__name__}_{config['stage_id']}",
        worker_id=config["worker_id"],
        timeout=config["timeout"],
    )


def make_coordinator_process(w_cls, c_ctx, shutdown, shutdown_notify, config):
    context = mp.get_context(c_ctx)
    context = cast(Union[SpawnContext, ForkContext], context)
    return context.Process(
        target=make_coordinator,
        args=(w_cls, shutdown, shutdown_notify, config),
        daemon=True,
    )


def test_socket_file_not_found(mocker, base_test_config, caplog):
    mocker.patch("mosec.coordinator.CONN_MAX_RETRY", 5)
    mocker.patch("mosec.coordinator.CONN_CHECK_INTERVAL", 0.01)

    c_ctx = base_test_config.pop("c_ctx")
    shutdown = mp.get_context(c_ctx).Event()
    shutdown_notify = mp.get_context(c_ctx).Event()

    with CleanDirContext(), caplog.at_level(logging.ERROR):
        _ = make_coordinator(
            EchoWorkerJSON, shutdown, shutdown_notify, base_test_config
        )
        record = caplog.records[0]
        assert "cannot find the socket file" in record.message


def test_incorrect_socket_file(mocker, base_test_config, caplog):
    mocker.patch("mosec.coordinator.CONN_MAX_RETRY", 5)
    mocker.patch("mosec.coordinator.CONN_CHECK_INTERVAL", 0.01)

    sock_addr = join(SOCKET_PREFIX, f"ipc_{EchoWorkerJSON.__name__}_1.socket")
    c_ctx = base_test_config.pop("c_ctx")
    shutdown = mp.get_context(c_ctx).Event()
    shutdown_notify = mp.get_context(c_ctx).Event()

    with CleanDirContext():
        os.makedirs(SOCKET_PREFIX, exist_ok=False)
        # create non-socket file
        open(sock_addr, "w", encoding="utf-8").close()

        with caplog.at_level(logging.ERROR):
            _ = make_coordinator(
                EchoWorkerJSON, shutdown, shutdown_notify, base_test_config
            )
            record = caplog.records[0]
            assert "connection error" in record.message

    with CleanDirContext():
        os.makedirs(SOCKET_PREFIX, exist_ok=False)
        # bind to a socket file to which no server is listening
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(sock_addr)

        with caplog.at_level(logging.ERROR):
            _ = make_coordinator(
                EchoWorkerJSON, shutdown, shutdown_notify, base_test_config
            )
            record = caplog.records[0]
            assert "socket connection error" in record.message


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
    ],
)
def test_echo_batch(base_test_config, test_data, worker, deserializer):
    """To test the batched data echo functionality.

    The batch size is automatically determined by the data's size.
    """
    # pylint: disable=too-many-locals
    c_ctx = base_test_config.pop("c_ctx")
    # whatever value greater than 1, so that coordinator
    # knows this stage enables batching
    base_test_config["max_batch_size"] = 8

    sock_addr = join(SOCKET_PREFIX, f"ipc_{worker.__name__}_1.socket")
    shutdown = mp.get_context(c_ctx).Event()
    shutdown_notify = mp.get_context(c_ctx).Event()

    with CleanDirContext():
        os.makedirs(SOCKET_PREFIX, exist_ok=False)

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(sock_addr)
        sock.listen()

        coordinator_process = make_coordinator_process(
            worker,
            c_ctx,
            shutdown,
            shutdown_notify,
            base_test_config,
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
            got_states = []
            got_payloads = []
            while got_batch_size > 0:
                got_batch_size -= 1
                got_ids.append(conn.recv(4))
                got_states.append(struct.unpack("!H", conn.recv(2))[0])
                got_length = struct.unpack("!I", conn.recv(4))[0]
                got_payloads.append(_recv_all(conn, got_length))
            assert got_flag == HTTPStatusCode.OK
            assert got_ids == sent_ids
            assert got_states == [State.INGRESS | State.EGRESS] * len(sent_ids)
            assert all(
                deserializer(x) == deserializer(y)
                for x, y in zip(got_payloads, sent_payloads)
            )
            shutdown.set()
            # wait for socket timeout, make the client not read closed socket
            time.sleep(PROTOCOL_TIMEOUT)
        except Exception as err:
            shutdown.set()
            raise err
