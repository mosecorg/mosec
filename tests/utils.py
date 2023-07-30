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

"""Useful functions for test."""

from __future__ import annotations

import contextlib
import os
import random
import socket
import struct
import time
from http import HTTPStatus
from io import BytesIO
from typing import TYPE_CHECKING, List, Tuple, Union

from mosec.coordinator import STATE_EGRESS, STATE_INGRESS

if TYPE_CHECKING:
    from tests.mock_socket import Socket as mock_socket


def imitate_controller_send(
    sock: Union[mock_socket, socket.socket], data: List[bytes]
) -> Tuple[List[bytes], List[bytes]]:
    # explicit byte format here for sanity check
    # placeholder flag, should be discarded by receiver
    header = struct.pack("!HH", HTTPStatus.OK, len(data))
    buf = BytesIO()
    buf.write(header)
    sent_ids = []
    sent_payloads = []
    for datum in data:
        tid = struct.pack("!I", random.randint(1, 100))
        sent_ids.append(tid)
        sent_payloads.append(datum)
        length = struct.pack("!I", len(datum))
        buf.write(tid)
        buf.write(struct.pack("!H", STATE_EGRESS | STATE_INGRESS))  # task state
        buf.write(length)
        buf.write(datum)

    sock.sendall(buf.getbuffer())  # type: ignore
    return sent_ids, sent_payloads


def wait_for_port_open(
    host: str = "127.0.0.1", port: int = 8000, timeout: int = 10
) -> bool:
    start_time = time.monotonic()
    while time.monotonic() - start_time < timeout:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.connect((host, port))
            sock.shutdown(socket.SHUT_RDWR)
            return True
        except (ConnectionRefusedError, OSError):
            pass
        finally:
            sock.close()
        time.sleep(0.1)
    return False


def wait_for_port_free(
    host: str = "127.0.0.1", port: int = 8000, timeout: int = 5
) -> bool:
    start_time = time.monotonic()
    while time.monotonic() - start_time < timeout:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.connect((host, port))
            sock.shutdown(socket.SHUT_RDWR)
        except (ConnectionRefusedError, OSError):
            return True
        finally:
            sock.close()
        time.sleep(0.1)
    return False


@contextlib.contextmanager
def env_context(**kwargs):
    """Set environment variables for testing."""
    old_env = os.environ.copy()
    os.environ.update(kwargs)
    yield
    os.environ = old_env
