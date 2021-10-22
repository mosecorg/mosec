import logging
import os
import signal
import socket
import struct
import time
import traceback
from multiprocessing.synchronize import Event
from typing import Callable, Type

from .errors import DecodingError, ValidationError
from .protocol import Protocol
from .worker import Worker

logger = logging.getLogger(__name__)


CONN_MAX_RETRY = 10
CONN_CHECK_INTERVAL = 1

STAGE_INGRESS = "ingress"
STAGE_EGRESS = "egress"

PROTOCOL_TIMEOUT = 2.0


class Coordinator:
    """
    This private class defines a set of coordination behaviors
    to receive tasks via `Protocol` and process them via `Worker`.
    """

    def __init__(
        self,
        worker: Type[Worker],
        max_batch_size: int,
        stage: str,
        shutdown: Event,
        shutdown_notify: Event,
        socket_prefix: str,
        stage_id: int,
        worker_id: int,
    ):
        """Initialize the mosec coordinator

        Args:
            worker (Worker): subclass of `mosec.Worker` implemented by users.
            max_batch_size (int): maximum batch size for this worker.
            stage (str): identifier to distinguish the first and last stages.
            shutdown (Event): `multiprocessing.synchronize.Event` object for shutdown
                IPC.
            socket_prefix (str): prefix for the socket addresses.
            stage_id (int): identification number for worker stages.
            worker_id (int): identification number for worker processes at the same
                stage.
        """
        self.worker = worker()
        self.worker._set_mbs(max_batch_size)
        self.worker._set_stage(stage)
        self.worker._set_id(worker_id)

        self.name = f"<{stage_id}|{worker.__name__}|{worker_id}>"

        self.protocol = Protocol(
            name=self.name,
            addr=os.path.join(socket_prefix, f"ipc_{stage_id}.socket"),
            timeout=PROTOCOL_TIMEOUT,
        )

        # ignore termination & interruption signal
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        self.shutdown = shutdown
        self.shutdown_notify = shutdown_notify

        self.init_worker()
        self.init_protocol()
        self.run()

    def exit(self):
        logger.info(f"{self.name} exiting...")

    def init_protocol(self):
        """Check socket readiness"""
        retry_count = 0
        while retry_count < CONN_MAX_RETRY and not self.shutdown.is_set():
            if os.path.exists(self.protocol.addr):
                return
            retry_count += 1
            logger.debug(
                f"{self.name} trying to find the socket file: {self.protocol.addr}"
                f" ({retry_count}/{CONN_MAX_RETRY})"
            )
            time.sleep(CONN_CHECK_INTERVAL)
            continue

        logger.error(f"{self.name} cannot find the socket file: {self.protocol.addr}")
        self.exit()

    def init_worker(self):
        """Optional warmup to allocate resources (useful for GPU workload)"""
        if not self.shutdown.is_set():
            if self.worker.example is not None:
                try:
                    self.worker.forward(self.worker.example)
                    logger.info(f"{self.name} warmup successfully")
                except Exception as err:
                    logger.error(
                        f"{self.name} warmup failed: {err}\nplease ensure"
                        " worker's example meets its forward input format"
                    )

    def run(self):
        """Maintain the protocol connection and run the coordination"""
        while not self.shutdown.is_set():
            # reconnect if needed
            try:
                self.protocol.open()
            except OSError as err:
                if not self.shutdown_notify.is_set():
                    logger.error(f"{self.name} socket connection error: {err}")
                break

            self.coordinate()

    def get_decoder(self) -> Callable:
        if STAGE_INGRESS in self.worker._stage:
            return self.worker.deserialize
        return self.worker._deserialize_ipc

    def get_encoder(self) -> Callable:
        if STAGE_EGRESS in self.worker._stage:
            return self.worker.serialize
        return self.worker._serialize_ipc

    def coordinate(self):
        """Start coordinating the protocol's communication and worker's forward pass"""
        decoder = self.get_decoder()
        encoder = self.get_encoder()
        while not self.shutdown.is_set():
            try:
                _, ids, payloads = self.protocol.receive()
            except socket.timeout:
                continue
            except (struct.error, OSError) as err:
                if not self.shutdown_notify.is_set():
                    logger.error(f"{self.name} socket receive error: {err}")
                break

            try:
                data = [decoder(item) for item in payloads]
                data = (
                    self.worker.forward(data)
                    if self.worker._max_batch_size > 1
                    else (self.worker.forward(data[0]),)
                )
                status = self.protocol.FLAG_OK
                payloads = [encoder(item) for item in data]
                if len(data) != len(payloads):
                    raise ValueError(
                        "returned data doesn't match the input data:"
                        f"input({len(data)})!=output({len(payloads)})"
                    )
            except DecodingError as err:
                err_msg = str(err).replace("\n", " - ")
                err_msg = (
                    err_msg if len(err_msg) else "cannot deserialize request bytes"
                )
                logger.info(f"{self.name} decoding error: {err_msg}")
                status = self.protocol.FLAG_BAD_REQUEST
                payloads = (f"decoding error: {err_msg}".encode(),)
            except ValidationError as err:
                err_msg = str(err)
                err_msg = err_msg if len(err_msg) else "invalid data format"
                logger.info(f"{self.name} validation error: {err_msg}")
                status = self.protocol.FLAG_VALIDATION_ERROR
                payloads = (f"validation error: {err_msg}".encode(),)
            except Exception:
                logger.warning(traceback.format_exc().replace("\n", " "))
                status = self.protocol.FLAG_INTERNAL_ERROR
                payloads = ("inference internal error".encode(),)

            try:
                self.protocol.send(status, ids, payloads)
            except OSError as err:
                logger.error(f"{self.name} socket send error: {err}")
                break

        self.protocol.close()
        time.sleep(CONN_CHECK_INTERVAL)
