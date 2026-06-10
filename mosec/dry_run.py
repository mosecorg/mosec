# Copyright 2023 MOSEC Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Dry run the service."""

from __future__ import annotations

import json
import resource
import signal
import sys
import time
from multiprocessing.context import SpawnContext, SpawnProcess
from typing import TYPE_CHECKING, Any, Dict, List, Tuple, Union

from mosec.env import env_var_context
from mosec.log import get_internal_logger
from mosec.runtime import Runtime
from mosec.worker import Worker

if TYPE_CHECKING:
    from multiprocessing.connection import PipeConnection  # type: ignore
    from multiprocessing.synchronize import Event

logger = get_internal_logger()


def _get_memory_metrics() -> Dict[str, Any]:
    """Collect memory metrics using stdlib resource module."""
    usage = resource.getrusage(resource.RUSAGE_SELF)
    rss = usage.ru_maxrss
    # On macOS, ru_maxrss is in bytes; on Linux, it's in kilobytes
    if sys.platform != "darwin":
        rss *= 1024
    return {"max_rss_bytes": rss}


def _try_reset_gpu_peak_memory():
    """Reset GPU peak memory stats if torch.cuda is available."""
    try:
        import torch  # pylint: disable=import-outside-toplevel

        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
    except ImportError:
        pass


def _get_gpu_metrics() -> Dict[str, Any]:
    """Collect GPU metrics if available (torch.cuda or pynvml)."""
    metrics: Dict[str, Any] = {}
    try:
        import torch  # pylint: disable=import-outside-toplevel

        if torch.cuda.is_available():
            metrics["gpu_peak_memory_bytes"] = torch.cuda.max_memory_allocated()
    except ImportError:
        pass

    try:
        # pylint: disable=import-outside-toplevel
        from pynvml import (
            nvmlDeviceGetHandleByIndex,
            nvmlDeviceGetMemoryInfo,
            nvmlDeviceGetUtilizationRates,
            nvmlInit,
            nvmlShutdown,
        )

        nvmlInit()
        try:
            handle = nvmlDeviceGetHandleByIndex(0)
            mem = nvmlDeviceGetMemoryInfo(handle)
            util = nvmlDeviceGetUtilizationRates(handle)
            metrics.setdefault("gpu_memory_used_bytes", mem.used)
            metrics["gpu_memory_total_bytes"] = mem.total
            metrics["gpu_utilization_pct"] = util.gpu
        finally:
            nvmlShutdown()
    except Exception:  # pylint: disable=broad-except
        pass

    return metrics


def dry_run_func(
    worker_cls: type[Worker],
    batch: int,
    receiver: PipeConnection,
    sender: PipeConnection,
    ingress: bool,
    shutdown_notify: Event,
    metrics_sender: PipeConnection,
):
    """Dry run simulation function."""
    worker = worker_cls()
    while not shutdown_notify.is_set():
        if receiver.poll(timeout=0.1):
            break

    if shutdown_notify.is_set():
        return

    try:
        data = receiver.recv() if ingress else worker.deserialize(receiver.recv_bytes())
        logger.info("%s received %s", worker, data)

        _try_reset_gpu_peak_memory()
        cpu_before = time.process_time()

        data = worker.forward([data])[0] if batch > 1 else worker.forward(data)

        cpu_after = time.process_time()
        stage_metrics: Dict[str, Any] = {
            "stage": worker_cls.__name__,
            "cpu_time_seconds": cpu_after - cpu_before,
            **_get_memory_metrics(),
            **_get_gpu_metrics(),
        }
        metrics_sender.send(stage_metrics)

        logger.info("%s inference result: %s", worker, data)
        data = worker.serialize(data)
        sender.send_bytes(data)
    # pylint: disable=broad-except
    except Exception as err:
        logger.error("get error in %s: %s", worker, err)
        shutdown_notify.set()


class Pool:
    """Process pool for dry run."""

    def __init__(self, process_context: SpawnContext, shutdown_notify: Event):
        """Initialize a process pool.

        Args:
            process_context: server context of spawn process
            shutdown_notify: event of server will shutdown

        """
        self.process_context = process_context
        self.shutdown_notify = shutdown_notify

        self.processes: List[SpawnProcess] = []
        self.sender_pipes: List[PipeConnection] = []
        self.receiver_pipes: List[PipeConnection] = []
        self.metrics_receivers: List[PipeConnection] = []

    def new_pipe(self):
        """Create new pipe for dry run workers to communicate."""
        receiver, sender = self.process_context.Pipe(duplex=False)
        self.sender_pipes.append(sender)
        self.receiver_pipes.append(receiver)

    def start_worker(self, worker_runtime: Runtime, init: bool):
        """Start the worker process for dry run.

        Args:
            worker_runtime: worker runtime to start
            init: whether the worker is tried to start at the first time

        """
        self.new_pipe()
        metrics_receiver, metrics_sender = self.process_context.Pipe(duplex=False)
        self.metrics_receivers.append(metrics_receiver)
        coordinator = self.process_context.Process(
            target=dry_run_func,
            args=(
                worker_runtime.worker,
                worker_runtime.max_batch_size,
                self.receiver_pipes[-2],
                self.sender_pipes[-1],
                init,
                self.shutdown_notify,
                metrics_sender,
            ),
            daemon=True,
        )

        with env_var_context(worker_runtime.env, 0):
            coordinator.start()

        self.processes.append(coordinator)

    def probe_worker_liveness(self) -> Tuple[Union[int, None], Union[int, None]]:
        """Check every worker is running/alive.

        Returns:
            index: index of the first failed worker
            exitcode: exitcode of the first failed worker

        """
        for i, process in enumerate(self.processes):
            if process.exitcode is not None:
                return i, process.exitcode
        return None, None

    def wait_all(self) -> Tuple[Union[int, None], Union[int, None]]:
        """Blocking until all worker to end or one failed.

        Returns:
            index: index of the first failed worker
            exitcode: exitcode of the first failed worker

        """
        for i, process in enumerate(self.processes):
            process.join()
            if process.exitcode != 0:
                return i, process.exitcode
        return None, None

    def first_last_pipe(self):
        """Get first sender and last receiver pipes."""
        return self.sender_pipes[0], self.receiver_pipes[-1]

    def collect_metrics(self, timeout: float = 5.0) -> List[Dict[str, Any]]:
        """Collect metrics from all worker stages.

        Args:
            timeout: seconds to wait for each worker's metrics.

        Returns:
            List of per-stage metrics dicts.

        """
        results: List[Dict[str, Any]] = []
        for receiver in self.metrics_receivers:
            if receiver.poll(timeout):
                results.append(receiver.recv())
        return results


class DryRunner:
    """Dry run the full stage.

    If examples are provided in the ingress :py:class:`Worker <mosec.worker.Worker>`,
    they will be used to pass through all the stages.

    For each stage, there will be only 1 worker. If `env` is provided during
    :py:meth:`append_worker <mosec.server.Server.append_worker>`, the 1st one
    will be used.
    """

    def __init__(self, router: Dict[str, List[Runtime]]):
        """Init dry runner."""
        self.router = router
        self.process_context: SpawnContext = SpawnContext()
        self.shutdown_notify: Event = self.process_context.Event()

        signal.signal(signal.SIGTERM, self.terminate)
        signal.signal(signal.SIGINT, self.terminate)

    def terminate(self, signum, framestack):
        """Terminate the dry run."""
        logger.info("received terminate signal [%s] %s", signum, framestack)
        self.shutdown_notify.set()

    def run(self):
        """Execute the dry run process."""
        for endpoint, runtimes in self.router.items():
            logger.info(
                "init dry run for endpoint %s with %s",
                endpoint,
                [runtime.name for runtime in runtimes],
            )

            pool = Pool(self.process_context, self.shutdown_notify)
            pool.new_pipe()
            for i, worker_runtime in enumerate(runtimes):
                pool.start_worker(worker_runtime, i == 0)

            logger.info("dry run init successful")
            self.warmup(runtimes, pool)

            logger.info("wait for worker init done")
            if not self.shutdown_notify.is_set():
                self.shutdown_notify.set()

            failed, exitcode = pool.wait_all()
            if failed is not None:
                logger.warning(
                    "detect %s with abnormal exit code %d",
                    runtimes[failed].name,
                    exitcode,
                )
                sys.exit(exitcode)

            self.shutdown_notify.clear()
        logger.info("dry run exit")

    def warmup(self, runtimes: List[Runtime], pool: Pool):
        """Warmup the service.

        If neither `example` nor `multi_examples` is provided, it will only
        init the worker class.
        """
        ingress = runtimes[0].worker
        example = None
        if ingress.example:
            example = ingress.example
        elif ingress.multi_examples:
            assert isinstance(ingress.multi_examples, list), (
                "`multi_examples` should be a list of data"
            )
            example = ingress.multi_examples[0]

        if not example:
            logger.info("cannot find the example in the 1st stage worker, skip warmup")
            return

        sender, receiver = pool.first_last_pipe()
        start_time = time.perf_counter()
        sender.send(example)

        while not self.shutdown_notify.is_set():
            if receiver.poll(0.1):
                break
            # liveness probe
            failed, exitcode = pool.probe_worker_liveness()
            if failed is not None:
                logger.warning(
                    "worker %s exit with code %d",
                    runtimes[failed].name,
                    exitcode,
                )
                self.shutdown_notify.set()
                break

        if self.shutdown_notify.is_set():
            sys.exit(1)

        res = receiver.recv_bytes()
        duration = time.perf_counter() - start_time

        stage_metrics = pool.collect_metrics()
        num_stages = len(runtimes)
        if len(stage_metrics) < num_stages:
            logger.warning(
                "only received metrics from %d/%d stages"
                " (some workers may have failed before reporting)",
                len(stage_metrics),
                num_stages,
            )

        result = {
            "request": example,
            "result_size": len(res),
            "warmup_duration": duration,
        }
        if stage_metrics:
            result["stage_metrics"] = stage_metrics
        logger.info("dry run result: %s", json.dumps(result, default=str))
