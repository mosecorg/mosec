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

"""The Coordinator is used to control the data flow between `Worker` and `Server`."""

import os
import signal
import socket
import struct
import time
import traceback
from contextlib import contextmanager
from multiprocessing.synchronize import Event
from typing import Any, Callable, Optional, Sequence, Tuple, Type

from mosec.errors import MosecError, MosecTimeoutError
from mosec.ipc import IPCWrapper
from mosec.log import get_internal_logger
from mosec.protocol import HTTPStautsCode, Protocol
from mosec.worker import Worker

logger = get_internal_logger()


CONN_MAX_RETRY = 10
CONN_CHECK_INTERVAL = 1

STAGE_INGRESS = "ingress"
STAGE_EGRESS = "egress"

PROTOCOL_TIMEOUT = 2.0


@contextmanager
def set_mosec_timeout(duration: int):
    """Context manager to set a timeout for a code block.

    Args:
        duration (float): the duration in seconds before timing out
    """

    def handler(signum, frame):
        raise MosecTimeoutError(
            f"[{signum}]`forward` timeout after {duration}s: {frame}"
        )

    signal.signal(signal.SIGALRM, handler)
    signal.alarm(duration)
    try:
        yield
    finally:
        signal.alarm(0)


class Coordinator:
    """Coordinator controls the data flow.

    This private class defines a set of coordination behaviors
    to receive tasks via `Protocol` and process them via `Worker`.
    """

    # pylint: disable=too-many-arguments
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
        ipc_wrapper: Optional[Callable[..., IPCWrapper]],
        timeout: int,
    ):
        """Initialize the mosec coordinator.

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
            ipc_wrapper (IPCWrapper): IPC wrapper class to be initialized.
            timeout (int): timeout for the `forward` function.

        Raises:
            TypeError: ipc_wrapper should inherit from `IPCWrapper`
        """
        self.worker = worker()
        self.worker.worker_id = worker_id
        self.worker.max_batch_size = max_batch_size
        self.worker.stage = stage
        self.timeout = timeout
        self.name = f"<{stage_id}|{worker.__name__}|{worker_id}>"

        self.protocol = Protocol(
            name=self.name,
            addr=os.path.join(socket_prefix, f"ipc_{stage_id}.socket"),
            timeout=PROTOCOL_TIMEOUT,
        )

        # optional plugin features - ipc wrapper
        self.ipc_wrapper: Optional[IPCWrapper] = None
        if ipc_wrapper is not None:
            self.ipc_wrapper = ipc_wrapper()
            if not issubclass(type(self.ipc_wrapper), IPCWrapper):
                raise TypeError(
                    "ipc_wrapper must be the subclass of mosec.plugins.IPCWrapper"
                )

        # ignore termination & interruption signal
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        self.shutdown = shutdown
        self.shutdown_notify = shutdown_notify

        self.warmup()
        self.init_protocol()
        self.run()

    def init_protocol(self):
        """Check socket readiness."""
        retry_count = 0
        while retry_count < CONN_MAX_RETRY and not self.shutdown.is_set():
            if os.path.exists(self.protocol.addr):
                return
            retry_count += 1
            logger.debug(
                "%s is trying to find the socket file: %s (%d/%d)",
                self.name,
                self.protocol.addr,
                retry_count,
                CONN_MAX_RETRY,
            )
            time.sleep(CONN_CHECK_INTERVAL)
            continue

        logger.error(
            "%s cannot find the socket file: %s, will shutdown",
            self.name,
            self.protocol.addr,
        )

    def warmup(self):
        """Warmup to allocate resources (useful for GPU workload)[Optional]."""
        need_warmup = self.worker.example or self.worker.multi_examples
        if self.shutdown.is_set() or not need_warmup:
            return
        try:
            # Prioritize multi_examples if both appear.
            if self.worker.multi_examples:
                num_eg = len(self.worker.multi_examples)
                for i, example in enumerate(self.worker.multi_examples):
                    self.worker.forward(example)
                    logger.debug(
                        "warming up... (%d/%d)",
                        i + 1,
                        num_eg,
                    )
            else:
                self.worker.forward(self.worker.example)
            logger.info("%s warmup successfully", self.name)
        # pylint: disable=broad-except
        except Exception:
            logger.error(
                "%s warmup failed: %s, please ensure"
                " worker's example meets its forward input format",
                self.name,
                traceback.format_exc().replace("\n", " "),
            )

    def run(self):
        """Maintain the protocol connection and run the coordination."""
        while not self.shutdown.is_set():
            # reconnect if needed
            try:
                self.protocol.open()
            except OSError as err:
                if not self.shutdown_notify.is_set():
                    logger.error("%s socket connection error: %s", self.name, err)
                break

            self.coordinate()

    def get_decoder(self) -> Callable[[bytes], Any]:
        """Get the decoder function for this stage.

        The first stage will use the worker's deserialize function.
        """
        if STAGE_INGRESS in self.worker.stage:
            return self.worker.deserialize
        return self.worker.deserialize_ipc

    def get_encoder(self) -> Callable[[Any], bytes]:
        """Get the encoder function for this stage.

        The last stage will use the worker's serialize function.
        """
        if STAGE_EGRESS in self.worker.stage:
            return self.worker.serialize
        return self.worker.serialize_ipc

    def get_protocol_recv(
        self,
    ) -> Callable[[], Tuple[bytes, Sequence[bytes], Sequence[bytes]]]:
        """Get the protocol receive function for this stage.

        IPC wrapper will be used if it's provided and the stage is not the first one.
        """
        if STAGE_INGRESS in self.worker.stage or self.ipc_wrapper is None:
            return self.protocol.receive

        # TODO(kemingy) find a better way
        def wrapped_recv() -> Tuple[bytes, Sequence[bytes], Sequence[bytes]]:
            flag, ids, payloads = self.protocol.receive()
            payloads = self.ipc_wrapper.get(  # type: ignore
                [bytes(x) for x in payloads]
            )
            return flag, ids, payloads

        return wrapped_recv

    def get_protocol_send(
        self,
    ) -> Callable[[int, Sequence[bytes], Sequence[bytes]], None]:
        """Get the protocol send function for this stage.

        IPC wrapper will be used if it's provided and the stage is not the last one.
        """
        if STAGE_EGRESS in self.worker.stage or self.ipc_wrapper is None:
            return self.protocol.send

        # TODO(kemingy) find a better way
        def wrapped_send(flag: int, ids: Sequence[bytes], payloads: Sequence[bytes]):
            if flag == HTTPStautsCode.OK:
                payloads = self.ipc_wrapper.put(payloads)  # type: ignore
            return self.protocol.send(flag, ids, payloads)

        return wrapped_send

    def coordinate(self):
        """Start coordinating the protocol's communication and worker's forward pass."""
        decoder = self.get_decoder()
        encoder = self.get_encoder()
        protocol_recv = self.get_protocol_recv()
        protocol_send = self.get_protocol_send()
        while not self.shutdown.is_set():
            try:
                _, ids, payloads = protocol_recv()
            except socket.timeout:
                continue
            except (struct.error, OSError) as err:
                if not self.shutdown_notify.is_set():
                    logger.error("%s failed to read from socket: %s", self.name, err)
                break

            # pylint: disable=broad-except
            length = len(payloads)
            try:
                data = [decoder(item) for item in payloads]
                with set_mosec_timeout(self.timeout):
                    data = (
                        self.worker.forward(data)
                        if self.worker.max_batch_size > 1
                        else (self.worker.forward(data[0]),)
                    )
                if len(data) != length:
                    raise ValueError(
                        "returned data size doesn't match the input data size:"
                        f"input({length})!=output({len(data)})"
                    )
                status = HTTPStautsCode.OK
                payloads = [encoder(item) for item in data]
            except (MosecError, MosecTimeoutError) as err:
                err_msg = str(err).replace("\n", " - ")
                err_msg = err_msg if err_msg else err.msg
                logger.info("%s %s: %s", self.name, err.msg, err_msg)
                status = err.code
                payloads = [f"{err.msg}: {err_msg}".encode()] * length
            except Exception:
                logger.warning(traceback.format_exc().replace("\n", " "))
                status = HTTPStautsCode.INTERNAL_ERROR
                payloads = ["inference internal error".encode()] * length

            try:
                protocol_send(status, ids, payloads)
            except OSError as err:
                logger.error("%s failed to send to socket: %s", self.name, err)
                break

        self.protocol.close()
        time.sleep(CONN_CHECK_INTERVAL)
