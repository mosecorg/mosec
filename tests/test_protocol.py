import json
import pickle
import random
import struct
from typing import List

import pytest

from mosec.protocol import Protocol

from .mock_socket import socket
from .utils import imitate_controller_send


def echo(p: Protocol, datum: List[bytes]):
    sent_status = random.choice([1, 2, 4, 8])

    sent_ids, sent_payloads = imitate_controller_send(p.socket, datum)

    _, got_ids, got_payloads = p.receive()  # client recv
    assert len(p.socket.buffer) == 0  # type: ignore
    assert got_ids == sent_ids
    assert all(
        [bytes(got_payloads[i]) == sent_payloads[i] for i in range(len(sent_payloads))]
    )

    p.send(sent_status, got_ids, got_payloads)  # client echo
    got_status, got_ids, got_payloads = p.receive()  # server recv (symmetric protocol)

    assert len(p.socket.buffer) == 0  # type: ignore
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
def test_echo(mock_protocol, test_data):
    mock_protocol.open()
    echo(mock_protocol, [pickle.dumps(x) for x in test_data])
    mock_protocol.close()
