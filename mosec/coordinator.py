import logging
import signal
import socket
import struct
import time
import traceback
from collections.abc import Callable
from multiprocessing.synchronize import Event
from os.path import join

from pydantic import BaseModel, ValidationError

from .protocol import Protocol
from .worker import Worker

logger = logging.getLogger(__name__)

EXIT_SUCCESS = 0
EXIT_FAIL = 1

CONN_MAX_RETRY = 10
CONN_CHECK_INTERVAL = 1
CONN_IGNORE_ERRNO = 56

STAGE_INGRESS = "ingress"
STAGE_EGRESS = "egress"
STAGE_INTERNAL = "x"


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
        req_schema: BaseModel,
        resp_schema: BaseModel,
    ):
        """Initialize the mosec coordinator

        Args:
            worker (Worker): subclass of `mosec.Worker` implemented by users.
            max_batch_size (int): maximum batch size for this worker.
            stage (str): identifier to distinguish the first and last stages.
            shutdown (Event): `multiprocessing.synchronize.Event` for shutdown IPC.
            socket_prefix (str): prefix for the socket addresses.
            stage_id (int): identification number for worker stages.
            worker_id (int): identification number for worker processes at the same
                stage.
            req_schema ([BaseModel]): subclass of `pydantic.BaseModel` to define
                input schema for validation if needed
            resp_schema ([BaseModel]): subclass of `pydantic.BaseModel` to define
                output schema for validation if needed
        """
        self.worker = worker()
        self.worker._set_mbs(max_batch_size)
        self.worker._set_stage(stage)

        self.req_schema = req_schema
        self.resp_schema = resp_schema

        self.name = f"<{stage_id+1}|{worker.__name__}|{worker_id+1}>"

        self.protocol = Protocol(
            name=self.name, addr=join(socket_prefix, f"{worker.__name__}.sock")
        )

        # ignore termination & interruption signal
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        self.shutdown = shutdown

        if self.init_protocol() == EXIT_SUCCESS:
            self.run()
        else:
            logger.warning(f"{self.name} protocol init failed")

    def init_protocol(self) -> int:
        """Establish protocol connection and returns status"""
        retry_count = 0
        while retry_count < CONN_MAX_RETRY:
            try:
                self.protocol.open()
                return EXIT_SUCCESS
            except ConnectionRefusedError as err:
                logger.warning(f"{self.name} socket connection refused: {err}")
                return EXIT_FAIL
            except FileNotFoundError:
                retry_count += 1
                logger.debug(
                    f"{self.name} trying to find the socket file: {self.protocol.addr} "
                    f"({retry_count}/{self.protocol_conn_retry})"
                )
                time.sleep(CONN_CHECK_INTERVAL)
                continue
        return EXIT_FAIL

    def run(self):
        """Maintain the protocol connection and run the coordination"""
        while not self.shutdown.is_set():
            # reconnect if needed
            try:
                self.protocol.open()
            except OSError as err:
                if (
                    err.errno != CONN_IGNORE_ERRNO
                ):  # ignore "Socket is already connected"
                    logger.error(f"{self.name} socket connection error: {err}")
                    break
            except ConnectionRefusedError as err:
                logger.error(f"{self.name} socket connection refused: {err}")
                break
            except FileNotFoundError:
                logger.error(f"{self.name} socket file not found")
                break

            if self.notify_readiness() == EXIT_FAIL:
                logger.warning(f"{self.name} readiness signal failed")
                break
            else:
                self.coordinate()

    def notify_readiness(self) -> int:
        try:
            self.protocol.send(self.protocol.FLAG_OK, [], [])
            return EXIT_SUCCESS
        except OSError as err:
            logger.error(f"{self.name} socket send error: {err}")
            return EXIT_FAIL

    def get_decoder(self) -> Callable:
        if self.worker._stage == STAGE_INGRESS:
            decoder = self.worker.deserialize

            def validate_decoder(data):
                return self.req_schema.parse_obj(decoder(data))

            return decoder if self.req_schema is None else validate_decoder
        else:
            decoder = self.worker._deserialize_ipc

    def get_encoder(self) -> Callable:
        if self.worker._stage == STAGE_EGRESS:
            encoder = self.worker.serialize

            def validate_encoder(data):
                assert isinstance(
                    data, self.resp_schema
                ), f"response {data} is not the instance of {self.resp_schema}"
                return encoder(data)

            return encoder if self.resp_schema is None else validate_encoder
        else:
            encoder = self.worker._serialize_ipc

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
                logger.error(f"{self.name} socket receive error: {err}")
                break

            try:
                data = [decoder(item) for item in payloads]
                data = (
                    self.worker(data)
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
            except ValidationError as err:
                err_msg = str(err).replace("\n", " - ")
                logger.info(f"{self.name} validation error: {err_msg}")
                status = self.protocol.FLAG_VALIDATION_ERROR
                payloads = (self.worker.pack(err.errors()),)
            except Exception:
                logger.warning(traceback.format_exc().replace("\n", " "))
                status = self.protocol.FLAG_INTERNAL_ERROR
                payloads = (self.worker.pack("Internal Error"),)

            try:
                self.protocol.send(status, ids, payloads)
            except OSError as err:
                logger.error(f"{self.name} socket send error: {err}")
                break

        self.protocol.close()
