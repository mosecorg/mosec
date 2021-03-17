import logging
import signal
import socket
import struct
import time
import traceback
from multiprocessing.synchronize import Event
from os.path import join

from pydantic import ValidationError

from .protocol import Protocol
from .worker import Worker

logger = logging.getLogger(__name__)

INIT_SUCCESS = True
INIT_FAIL = False
CONN_MAX_RETRY = 10
CHECK_INTERVAL = 1


class Coordinator:
    """
    This private class defines a set of coordination behaviors
    to receive tasks via `Protocol` and process them via `Worker`.
    """

    def __init__(
        self,
        worker: Worker,
        max_batch_size: int,
        stage: str,
        shutdown: Event,
        socket_prefix: str,
        stage_id: int,
        worker_id: int,
    ):
        """Initialize the mosec coordinator

        Args:
            worker (Worker): subclass of `mosec.Worker` implemented by users.
            max_batch_size (int): maximum batch size for this worker.
            stage (str): identifier to distinguish the first and last stages.
            shutdown (Event): `multiprocessing.synchronize.Event` for shutdown IPC.
            socket_prefix (str): prefix for the socket addresses.
            stage_id (int): identification number for worker stages.
            worker_id (int): identification number for worker processes at the same stage.
        """
        self.worker = worker()
        self.worker._set_mbs(max_batch_size)
        self.worker._set_stage(stage)

        self.name = f"<{stage_id+1}|{str(self.worker)}|{worker_id+1}>"

        self.protocol = Protocol(
            name=self.name, addr=join(socket_prefix, f"stage{stage_id}.sock")
        )

        # ignore termination & interruption signal
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        self.shutdown = shutdown

        if self.init_protocol() == INIT_SUCCESS:
            self.run()

    def init_protocol(self) -> bool:
        """Establish protocol connection and returns status"""
        retry_count = 0
        while retry_count < CONN_MAX_RETRY:
            try:
                self.protocol.open()
                return INIT_SUCCESS
            except ConnectionRefusedError as err:
                logger.warning(f"{self.name} socket connection refused: {err}")
                return INIT_FAIL
            except FileNotFoundError:
                retry_count += 1
                logger.debug(
                    f"{self.name} trying to find the socket file: {self.protocol.addr} "
                    f"({retry_count}/{self.protocol_conn_retry})"
                )
                time.sleep(CHECK_INTERVAL)
                continue
        else:
            logger.warning(f"{self.name} socket file not found")
            return INIT_FAIL

    def run(self):
        """Maintain the protocol connection and run the coordination"""
        while not self.shutdown.is_set():
            # reconnect if needed
            try:
                self.protocol.open()
            except OSError as err:
                if err.errno != 56:  # Socket is already connected
                    logger.error(f"{self.name} socket connection error: {err}")
                    break
            except ConnectionRefusedError as err:
                logger.error(f"{self.name} socket connection refused: {err}")
                break
            except FileNotFoundError:
                logger.error(f"{self.name} socket file not found")
                break
            self.coordinate()

    def coordinate(self):
        """Start coordinating the protocol's communication and worker's forward pass"""
        while not self.shutdown.is_set():
            try:
                ids, data = self.protocol.receive()
            except socket.timeout:
                continue
            except (struct.error, OSError) as err:
                logger.error(f"{self.name} socket receive error: {err}")
                break

            try:
                decoder = (
                    self.worker.unpack
                    if self.worker._stage == "ingress"
                    else self.worker._deserialize
                )
                encoder = (
                    self.worker.pack
                    if self.worker._stage == "egress"
                    else self.worker._serialize
                )
                data = [decoder(item) for item in data]
                data = (
                    self.worker(data)
                    if self.worker._max_batch_size > 1
                    else (self.worker.forward(data[0]),)
                )
                status = self.protocol.FLAG_OK
                data = [encoder(item) for item in data]
                if len(ids) != len(data):
                    raise ValueError(
                        "returned data doesn't match the input data:"
                        f"input({len(ids)})!=output({len(data)})"
                    )
            except ValidationError as err:
                err_msg = str(err).replace("\n", " - ")
                logger.info(f"{self.name} validation error: {err_msg}")
                status = self.protocol.FLAG_VALIDATION_ERROR
                data = (self.worker.pack(err.json().encode()),)
            except Exception:
                logger.warning(f"{self.name} internal error: {traceback.format_exc()}")
                status = self.protocol.FLAG_INTERNAL_ERROR
                data = (self.worker.pack("Internal Error".encode()),)

            try:
                self.protocol.send(ids, data, status)
            except OSError as err:
                logger.error(f"{self.name} socket send error: {err}")
                break

        self.protocol.close()
