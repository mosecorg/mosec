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

import enum
import os
import queue
import signal
import socket
import struct
import threading
import time
import traceback
from contextlib import contextmanager
from multiprocessing.synchronize import Event
from typing import Any, Optional, Sequence, Type

from mosec.errors import MosecError, MosecTimeoutError
from mosec.log import get_internal_logger
from mosec.protocol import HTTPStautsCode, Protocol
from mosec.worker import SSEWorker, Worker

logger = get_internal_logger()


CONN_MAX_RETRY = 10
CONN_CHECK_INTERVAL = 1


class State(enum.IntFlag):
    """Task state."""

    INGRESS = 0b1
    EGRESS = 0b10


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


class FakeSemaphore:
    """Fake semaphore interface for non-SSE workers."""

    def __init__(self, value: int = 1):
        """Not intend to be used by users."""
        self.value = value

    def acquire(self, timeout: Optional[float] = None):
        """Acquire the semaphore."""

    def release(self):
        """Release the semaphore."""

    __enter__ = acquire

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the context."""
        self.release()


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
        shutdown: Event,
        shutdown_notify: Event,
        socket_prefix: str,
        stage_name: str,
        worker_id: int,
        timeout: int,
    ):
        """Initialize the mosec coordinator.

        Args:
            worker: subclass of `mosec.Worker` implemented by users.
            max_batch_size: maximum batch size for this worker.
            shutdown: `multiprocessing.synchronize.Event` object for shutdown
                IPC.
            socket_prefix: prefix for the socket addresses.
            stage_name: identification name for this worker stage.
            worker_id: identification number for worker processes at the same
                stage.
            timeout: timeout for the `forward` function.
        """
        self.name = f"<{stage_name}|{worker_id}>"
        self.timeout = timeout
        self.current_ids: Sequence[bytes] = []
        self.semaphore = FakeSemaphore()  # type: ignore

        self.worker = worker()
        self.worker.worker_id = worker_id
        self.worker.max_batch_size = max_batch_size
        self.worker.stage = stage_name

        self.protocol = Protocol(
            name=self.name,
            addr=os.path.join(socket_prefix, f"ipc_{stage_name}.socket"),
            timeout=PROTOCOL_TIMEOUT,
        )

        # ignore termination & interruption signal
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        self.shutdown = shutdown
        self.shutdown_notify = shutdown_notify

        # SSE support
        if issubclass(worker, SSEWorker):
            self.stream: queue.SimpleQueue = queue.SimpleQueue()
            self.semaphore: threading.Semaphore = threading.Semaphore()  # type: ignore
            self.worker._stream_queue = self.stream  # type: ignore
            self.worker._stream_semaphore = self.semaphore  # type: ignore
            threading.Thread(target=self.streaming, daemon=True).start()

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

    def streaming(self):
        """Send stream data from the worker to the server through the socket."""
        while not self.shutdown.is_set():
            try:
                text, index = self.stream.get(timeout=self.timeout)
                # encode the text with UTF-8
                payloads = (text.encode(),)
                ids = (self.current_ids[index],)
                self.protocol.send(
                    HTTPStautsCode.STREAM_EVENT, ids, (0,) * len(ids), payloads
                )
                self.semaphore.release()
            except queue.Empty:
                continue

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

    def decode(self, payload: bytes, state: int) -> Any:
        """Decode the payload with the state."""
        return (
            self.worker.deserialize(payload)
            if state & State.INGRESS
            else self.worker.deserialize_ipc(payload)
        )

    def encode(self, data: Any, state: int) -> bytes:
        """Encode the data with the state."""
        return (
            self.worker.serialize(data)
            if state & State.EGRESS
            else self.worker.serialize_ipc(data)
        )

    def coordinate(self):
        """Start coordinating the protocol's communication and worker's forward pass."""
        while not self.shutdown.is_set():
            try:
                # flag received from the server is not used
                _, ids, states, payloads = self.protocol.receive()
                # expose here to be used by stream event
                self.current_ids = ids
            except socket.timeout:
                continue
            except (struct.error, OSError) as err:
                if not self.shutdown_notify.is_set():
                    logger.error("%s failed to read from socket: %s", self.name, err)
                break

            # pylint: disable=broad-except
            length = len(payloads)
            try:
                data = [
                    self.decode(payload, state)
                    for (payload, state) in zip(payloads, states)
                ]
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
                payloads = [
                    self.encode(datum, state) for (datum, state) in zip(data, states)
                ]
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
                # pylint: disable=consider-using-with
                self.semaphore.acquire(timeout=self.timeout)
                self.protocol.send(status, ids, states, payloads)
            except OSError as err:
                logger.error("%s failed to send to socket: %s", self.name, err)
                break
            finally:
                self.semaphore.release()

        self.protocol.close()
        time.sleep(CONN_CHECK_INTERVAL)
