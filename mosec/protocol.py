import logging
import signal
import socket
import struct
import traceback
from itertools import zip_longest
from multiprocessing.synchronize import Event

from pydantic import ValidationError

from .worker import WorkerBase

logger = logging.getLogger(__name__)


class Protocol:
    """
    This class implemnets the protocol based on uds
    to communicate with the server and process the received tasks.
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
        addr: str,
        worker: WorkerBase,
        id: int,
        shutdown: Event,
        timeout=1.0,
    ):
        """Initialize the protocol

        Args:
            addr (str): socket address (in file system name space).
            worker (WorkerBase): worker that implements (by users) `__call__` as
                forward pass, and optionally `__repr__` for naming.
            id (int): worker id at the same stage.
            shutdown (Event): shutdown event to close this protocol.
            timeout (float, optional): socket timeout. Defaults to 1.0.
        """

        self.socket = socket.socket(
            socket.AF_UNIX,
            socket.SOCK_STREAM,
        )
        self.socket.settimeout(timeout)
        self.addr = addr
        self.worker = worker
        self.name = f"<{worker.__repr__}_{id}>"

        # ignore termination & interruption signal
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        self.shutdown = shutdown

    def communicate(self):
        """Start communicating with the server"""
        while not self.shutdown.is_set():
            try:
                self.socket.connect(self.addr)
                logger.info(f"{self.name} socket connected to {self.addr}")
            except BrokenPipeError as err:
                logger.warning(f"{self.name} socket is broken: {err}")
                continue
            except FileNotFoundError as err:
                logger.warning(f"{self.name} socket file not found: {err}")
                break

            while not self.shutdown.is_set():
                try:
                    ids, data = self.receive()
                except socket.timeout:
                    continue
                except (struct.error, OSError) as err:
                    logger.warning(f"{self.name} struct unpack error: {err}")
                    break

                status = self.FLAG_OK
                try:
                    decoder = (
                        self.worker.unpack
                        if self.worker._stage == "ingress"
                        else self.worker.deserialize
                    )
                    encoder = (
                        self.worker.pack
                        if self.worker._stage == "egress"
                        else self.worker.serialize
                    )
                    data = [decoder(item) for item in data]
                    data = (
                        self.worker(data)
                        if self.worker._max_batch_size > 1
                        else (self.worker(data[0]),)
                    )
                    data = [encoder(item) for item in data]
                    if len(ids) != len(data):
                        raise ValueError(
                            "returned data doesn't match the input data:"
                            f"input({len(ids)})!=output({len(data)})"
                        )
                except ValidationError as err:
                    err_msg = str(err).replace("\n", " - ")
                    logger.info(f"{self.name} validation error: {err_msg}")
                    status = self.FLAG_VALIDATION_ERROR
                    err = err.json().encode()
                    data = (self.worker.pack(err),)
                except Exception:
                    logger.warning(
                        f"{self.name} internal error: {traceback.format_exc()}"
                    )
                    status = self.FLAG_INTERNAL_ERROR
                    data = (self.worker.pack("Internal Error".encode()),)
                try:
                    self.send(ids, data, status)
                except OSError as err:
                    logger.warning(f"{self.name} socket send error: {err}")
                    break

        self.stop()

    def receive(self):
        """Receive tasks from the server"""
        _ = self.socket.recv(self.LENGTH_TASK_FLAG)
        batch_size_bytes = self.socket.recv(self.LENGTH_TASK_BATCH)
        batch_size = struct.unpack(self.FORMAT_BATCH, batch_size_bytes)[0]
        ids, data = [], []

        while batch_size > 0:
            batch_size -= 1
            id_bytes = self.socket.recv(self.LENGTH_TASK_ID)
            length_bytes = self.socket.recv(self.LENGTH_TASK_BODY_LEN)
            length = struct.unpack(self.FORMAT_LENGTH, length_bytes)[0]
            payload = recv_all(self.socket, length)
            ids.append(id_bytes)
            data.append(payload)

        logger.debug(f"{self.name} received {ids}")
        return ids, data

    def send(self, ids, payloads, flag):
        """Send results to the server"""
        batch_size = len(ids)
        data = bytearray()
        data.extend(struct.pack(self.FORMAT_FLAG, flag))
        data.extend(struct.pack(self.FORMAT_BATCH, batch_size))

        for task_id, payload in zip_longest(ids, payloads, fillvalue=payloads[0]):
            length = struct.pack(self.FORMAT_LENGTH, len(payload))
            data.extend(task_id)
            data.extend(length)
            data.extend(payload)

        self.socket.sendall(data)
        logger.debug(f"{self.name} sent {ids}")

    def stop(self):
        """Close the socket connection"""
        self.socket.close()
        logger.info(f"{self.name} socket closed")


def recv_all(conn, length):
    buffer = bytearray(length)
    mv = memoryview(buffer)
    size = 0
    while size < length:
        packet = conn.recv_into(mv)
        mv = mv[packet:]
        size += packet
    return buffer
