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

"""Test protocol related logic."""

import json
import pickle
import random
import struct
from typing import List

import pytest

from mosec.coordinator import State
from mosec.protocol import Protocol
from tests.mock_socket import Socket
from tests.utils import imitate_controller_send


def echo(protocol: Protocol, data: List[bytes]):
    sent_flag = random.choice([1, 2, 4, 8])

    sent_ids, sent_payloads = imitate_controller_send(protocol.socket, data)

    _, got_ids, got_states, got_payloads = protocol.receive()  # client recv
    assert len(protocol.socket.buffer) == 0  # type: ignore
    assert got_ids == sent_ids
    assert all(
        bytes(got_payloads[i]) == sent_payloads[i] for i in range(len(sent_payloads))
    )
    got_payload_bytes = [bytes(x) for x in got_payloads]
    # client echo
    protocol.send(sent_flag, got_ids, got_states, got_payload_bytes)
    # server recv (symmetric protocol)
    got_flag, got_ids, got_states, got_payloads = protocol.receive()

    assert len(protocol.socket.buffer) == 0  # type: ignore
    assert struct.unpack("!H", got_flag)[0] == sent_flag
    assert got_states == [State.INGRESS | State.EGRESS] * len(sent_ids)
    assert got_ids == sent_ids
    assert all(
        bytes(got_payloads[i]) == sent_payloads[i] for i in range(len(sent_payloads))
    )


@pytest.fixture
def mock_protocol(mocker):
    mocker.patch("mosec.protocol.socket", Socket)
    protocol = Protocol(name="test", addr="mock.uds")
    return protocol


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
