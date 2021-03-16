import logging
import signal
import socket
import struct
import traceback
from multiprocessing.synchronize import Event
from os.path import join

from pydantic import ValidationError

from .protocol import Protocol
from .worker import Worker

logger = logging.getLogger(__name__)


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
        self.worker = worker()
        self.worker._set_mbs(max_batch_size)
        self.worker._set_stage(stage)

        self.name = f"<{stage_id+1}|{str(self.worker)}|{worker_id+1}>"

        self.protocol = Protocol(self.name)
        self.protocol.set_addr(join(socket_prefix, f"stage{stage_id}.sock"))

        # ignore termination & interruption signal
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        self.shutdown = shutdown

        self.coordinate()

    def coordinate(self):
        """Start communicating with the server and processing tasks"""
        while not self.shutdown.is_set():
            try:
                self.protocol.socket.connect(self.protocol.addr)
                logger.info(f"{self.name} socket connected to {self.protocol.addr}")
            except BrokenPipeError as err:
                logger.warning(f"{self.name} socket is broken: {err}")
                continue
            except FileNotFoundError as err:
                logger.warning(f"{self.name} socket file not found: {err}")
                break

            while not self.shutdown.is_set():
                try:
                    ids, data = self.protocol.receive()
                except socket.timeout:
                    continue
                except (struct.error, OSError) as err:
                    logger.warning(f"{self.name} struct unpack error: {err}")
                    break

                status = self.protocol.FLAG_OK
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
                    err = err.json().encode()
                    data = (self.worker.pack(err),)
                except Exception:
                    logger.warning(
                        f"{self.name} internal error: {traceback.format_exc()}"
                    )
                    status = self.protocol.FLAG_INTERNAL_ERROR
                    data = (self.worker.pack("Internal Error".encode()),)
                try:
                    self.protocol.send(ids, data, status)
                except OSError as err:
                    logger.warning(f"{self.name} socket send error: {err}")
                    break

        self.protocol.stop()
