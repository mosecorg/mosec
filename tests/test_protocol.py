import json
import pickle
import random
import struct
from typing import Any, List

import pytest

from mosec.protocol import Protocol

from .mock_socket import socket


def send_socket_buffer(p: Protocol, data):
    p.socket.buffer += data


def prepare_buffer(p: Protocol, l_data: List[Any]):
    # explicit byte format here for sanity check
    # placeholder flag, should be discarded by receiver
    header = struct.pack("!H", 0) + struct.pack("!H", len(l_data))
    body = b""
    sent_ids = []
    sent_payloads = []
    for data in l_data:
        tid = struct.pack("!I", random.randint(1, 100))
        sent_ids.append(tid)
        payloads = pickle.dumps(data)
        sent_payloads.append(payloads)
        length = struct.pack("!I", len(payloads))
        body += tid + length + payloads
    send_socket_buffer(p, header + body)
    return sent_ids, sent_payloads


def buffer_is_empty(p: Protocol):
    return len(p.socket.buffer) == 0


def echo(p: Protocol, datum: list):
    sent_status = random.choice([1, 2, 4, 8])

    sent_ids, sent_payloads = prepare_buffer(p, datum)

    _, got_ids, got_payloads = p.receive()  # client recv
    assert buffer_is_empty(p)
    assert got_ids == sent_ids
    assert all(
        [bytes(got_payloads[i]) == sent_payloads[i] for i in range(len(sent_payloads))]
    )

    p.send(sent_status, got_ids, got_payloads)  # client echo
    got_status, got_ids, got_payloads = p.receive()  # server recv (symmetric protocol)

    assert buffer_is_empty(p)
    assert struct.unpack("!H", got_status)[0] == sent_status
    assert got_ids == sent_ids
    assert all(
        [bytes(got_payloads[i]) == sent_payloads[i] for i in range(len(sent_payloads))]
    )


@pytest.fixture
def mock_protocol(mocker):
    mocker.patch("mosec.protocol.socket", socket)
    p = Protocol(name="test", addr="mock.uds")
    return p


@pytest.mark.parametrize(
    "test_data",
    [
        [],
        ["test"],
        [1, 2, 3],
        [
            json.dumps({"rid": "147982364", "data": "im_b64_str"}),
            json.dumps({"rid": "147982365", "data": "another_im_b64_str"}),
        ]
        * random.randint(1, 20),
    ],
)
def test_protocol(mock_protocol, test_data):
    mock_protocol.open()
    echo(mock_protocol, test_data)
    mock_protocol.close()
