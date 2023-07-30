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

"""Server-Worker communication protocol."""

import logging
import socket
import struct
import warnings
from enum import IntFlag
from io import BytesIO
from typing import Sequence, Tuple

from mosec.log import get_internal_logger

logger = get_internal_logger()

IPC_LARGE_DATA_SIZE = 1024 * 1024  # set as 1 MB


class HTTPStautsCode(IntFlag):
    """HTTP status code flag."""

    OK = 1  # 200
    BAD_REQUEST = 2  # 400
    VALIDATION_ERROR = 4  # 422
    INTERNAL_ERROR = 8  # 500
    TIMEOUT_ERROR = 16  # 408

    # special one, indicate that it's a SSE
    STREAM_EVENT = 32768


class Protocol:
    """IPC protocol.

    This private class implements the client-side protocol through Unix domain socket
    to communicate with the server.
    """

    # byte formats (https://docs.python.org/3/library/struct.html#format-characters)
    FORMAT_FLAG = "!H"
    FORMAT_BATCH = "!H"
    FORMAT_ID = "!I"
    FORMAT_LENGTH = "!I"
    FORMAT_STATE = "!H"

    # lengths
    LENGTH_TASK_FLAG = 2
    LENGTH_TASK_BATCH = 2
    LENGTH_TASK_ID = 4
    LENGTH_TASK_STATE = 2
    LENGTH_TASK_BODY_LEN = 4

    def __init__(
        self,
        name: str,
        addr: str,
        timeout: float = 2.0,
    ):
        """Initialize the protocol client.

        Args:
            name (str): name of its belonging coordinator.
            addr (str): Unix domain socket address in file system's namespace.
            timeout (float, optional): socket timeout. Defaults to 2.0 seconds.
        """
        self.socket = socket.socket(
            socket.AF_UNIX,
            socket.SOCK_STREAM,
        )
        self.socket.settimeout(timeout)
        self.name = name
        self.addr = addr

    def receive(self) -> Tuple[bytes, Sequence[bytes], Sequence[int], Sequence[bytes]]:
        """Receive tasks from the server."""
        flag = self.socket.recv(self.LENGTH_TASK_FLAG)
        batch_size_bytes = self.socket.recv(self.LENGTH_TASK_BATCH)
        batch_size = struct.unpack(self.FORMAT_BATCH, batch_size_bytes)[0]
        ids, states, payloads = [], [], []
        total_bytes = 0

        while batch_size > 0:
            batch_size -= 1
            id_bytes = self.socket.recv(self.LENGTH_TASK_ID)
            state_bytes = self.socket.recv(self.LENGTH_TASK_STATE)
            length_bytes = self.socket.recv(self.LENGTH_TASK_BODY_LEN)
            length = struct.unpack(self.FORMAT_LENGTH, length_bytes)[0]
            payload = _recv_all(self.socket, length)
            ids.append(id_bytes)
            states.append(struct.unpack(self.FORMAT_STATE, state_bytes)[0])
            payloads.append(payload)
            total_bytes += length

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "%s received %d tasks with ids: %s",
                self.name,
                len(ids),
                struct.unpack("!" + "I" * len(ids), b"".join(ids)),
            )

        if total_bytes > IPC_LARGE_DATA_SIZE:
            warnings.warn(
                f"IPC data ({total_bytes} bytes) is large, "
                "which may affect performance",
                RuntimeWarning,
            )
        return flag, ids, states, payloads

    def send(
        self,
        flag: int,
        ids: Sequence[bytes],
        states: Sequence[int],
        payloads: Sequence[bytes],
    ):
        """Send results to the server."""
        data = BytesIO()
        data.write(struct.pack(self.FORMAT_FLAG, flag))
        if len(ids) != len(payloads):
            raise ValueError("`ids` have different length with `payloads`")
        batch_size = len(ids)
        data.write(struct.pack(self.FORMAT_BATCH, batch_size))
        if batch_size > 0:
            for task_id, state, payload in zip(ids, states, payloads):
                data.write(task_id)
                data.write(struct.pack(self.FORMAT_STATE, state))
                data.write(struct.pack(self.FORMAT_LENGTH, len(payload)))
                data.write(payload)
        self.socket.sendall(data.getbuffer())
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "%s sent %d(%d) tasks with ids: %s",
                self.name,
                len(ids),
                flag,
                struct.unpack("!" + "I" * len(ids), b"".join(ids)),
            )

    def open(self):
        """Open the socket connection."""
        self.socket.connect(self.addr)
        logger.info("%s socket connected to %s", self.name, self.addr)

    def close(self):
        """Close the socket connection."""
        self.socket.close()
        logger.info("%s socket closed", self.name)


def _recv_all(conn, length):
    buffer = bytearray(length)
    view = memoryview(buffer)
    size = 0
    while size < length:
        packet = conn.recv_into(view)
        view = view[packet:]
        size += packet
    return buffer
