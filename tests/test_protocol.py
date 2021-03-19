import json
import pickle
import random
import struct
from typing import Any, List

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
    for i in range(len(l_data)):
        tid = struct.pack("!I", random.randint(1, 100))
        payloads = pickle.dumps(l_data[i])
        length = struct.pack("!I", len(payloads))
        sent_ids.append(tid)
        sent_payloads.append(payloads)
        body += tid + length + payloads
    send_socket_buffer(p, header + body)
    return sent_ids, sent_payloads


def buffer_is_empty(p: Protocol):
    return len(p.socket.buffer) == 0


def echo(p: Protocol, datum: list):
    sent_status = random.choice([1, 2, 4, 8])

    sent_ids, sent_payloads = prepare_buffer(p, datum)

    _, ids, payloads = p.receive()  # client recv
    p.send(sent_status, ids, payloads)  # client echo

    status, ids, payloads = p.receive()  # symmetric protocol

    assert buffer_is_empty(p)
    assert struct.unpack("!H", status)[0] == sent_status
    assert ids == sent_ids
    assert all(
        [bytes(payloads[i]) == sent_payloads[i] for i in range(len(sent_payloads))]
    )


def test_protocol(mocker):
    mocker.patch("mosec.protocol.socket", socket)
    p = Protocol(name="test", addr="mock.uds")
    p.open()
    echo(p, ["test"])
    echo(p, [1, 2, 3])
    echo(p, json.dumps({"rid": "147982364", "data": "im_b64_str"}))
    p.close()
