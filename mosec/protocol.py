import logging
import socket
import struct
from itertools import zip_longest

logger = logging.getLogger(__name__)


class Protocol:
    """
    This private class implements the client-side
    protocol based on uds to communicate with the
    server hosted on mosec controller side.
    """

    # byte formats (https://docs.python.org/3/library/struct.html#format-characters)
    FORMAT_FLAG = "!H"
    FORMAT_BATCH = "!H"
    FORMAT_ID = "!I"
    FORMAT_LENGTH = "!I"

    # flags
    FLAG_OK = 1  # 200
    FLAG_BAD_REQUEST = 2  # 400
    FLAG_VALIDATION_ERROR = 4  # 422
    FLAG_INTERNAL_ERROR = 8  # 500

    # lengths
    LENGTH_TASK_FLAG = 2
    LENGTH_TASK_BATCH = 2
    LENGTH_TASK_ID = 4
    LENGTH_TASK_BODY_LEN = 4

    def __init__(
        self,
        name: str,
        addr: str,
        timeout: float = 2.0,
    ):
        """Initialize the protocol client

        Args:
            name (str): name of its belonging coordinator.
            addr (str): unix domain socket address in file system's namespace.
            timeout (float, optional): socket timeout. Defaults to 2.0 seconds.
        """
        self.socket = socket.socket(
            socket.AF_UNIX,
            socket.SOCK_STREAM,
        )
        self.socket.settimeout(timeout)
        self.name = name
        self.addr = addr

    def receive(self):
        """Receive tasks from the server"""
        flag = self.socket.recv(self.LENGTH_TASK_FLAG)
        batch_size_bytes = self.socket.recv(self.LENGTH_TASK_BATCH)
        batch_size = struct.unpack(self.FORMAT_BATCH, batch_size_bytes)[0]
        ids, payloads = [], []

        while batch_size > 0:
            batch_size -= 1
            id_bytes = self.socket.recv(self.LENGTH_TASK_ID)
            length_bytes = self.socket.recv(self.LENGTH_TASK_BODY_LEN)
            length = struct.unpack(self.FORMAT_LENGTH, length_bytes)[0]
            payload = _recv_all(self.socket, length)
            ids.append(id_bytes)
            payloads.append(payload)

        logger.debug(f"{self.name} received {len(ids)} tasks with ids: {ids}")
        return flag, ids, payloads

    def send(self, flag, ids, payloads):
        """Send results to the server"""
        data = bytearray()
        data.extend(struct.pack(self.FORMAT_FLAG, flag))
        batch_size = len(ids)
        data.extend(struct.pack(self.FORMAT_BATCH, batch_size))
        if batch_size > 0:
            for task_id, payload in zip_longest(ids, payloads, fillvalue=payloads[0]):
                length = struct.pack(self.FORMAT_LENGTH, len(payload))
                data.extend(task_id)
                data.extend(length)
                data.extend(payload)

        self.socket.sendall(data)
        logger.debug(f"{self.name} sent {len(ids)} tasks with ids: {ids}")

    def open(self):
        """Open the socket connection"""
        self.socket.connect(self.addr)
        logger.info(f"{self.name} socket connected to {self.addr}")

    def close(self):
        """Close the socket connection"""
        self.socket.close()
        logger.info(f"{self.name} socket closed")


def _recv_all(conn, length):
    buffer = bytearray(length)
    mv = memoryview(buffer)
    size = 0
    while size < length:
        packet = conn.recv_into(mv)
        mv = mv[packet:]
        size += packet
    return buffer
