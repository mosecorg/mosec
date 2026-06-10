# Copyright 2026 MOSEC Authors
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

"""Test dry run metrics collection."""

from multiprocessing.context import SpawnContext
from typing import List

import pytest

from mosec.dry_run import (
    Pool,
    _get_gpu_metrics,
    _get_memory_metrics,
    dry_run_func,
)
from mosec.runtime import Runtime
from mosec.worker import Worker


class EchoWorker(Worker):
    def forward(self, data):
        return data


class BatchEchoWorker(Worker):
    def forward(self, data: List[dict]) -> List[dict]:
        return data


@pytest.fixture
def spawn_ctx():
    ctx = SpawnContext()
    shutdown_notify = ctx.Event()
    return ctx, shutdown_notify


@pytest.fixture
def dry_run_pipes(spawn_ctx):
    ctx, shutdown_notify = spawn_ctx
    data_receiver, data_sender = ctx.Pipe(duplex=False)
    result_receiver, result_sender = ctx.Pipe(duplex=False)
    metrics_receiver, metrics_sender = ctx.Pipe(duplex=False)
    return {
        "ctx": ctx,
        "shutdown_notify": shutdown_notify,
        "data_receiver": data_receiver,
        "data_sender": data_sender,
        "result_receiver": result_receiver,
        "result_sender": result_sender,
        "metrics_receiver": metrics_receiver,
        "metrics_sender": metrics_sender,
    }


def test_get_memory_metrics():
    metrics = _get_memory_metrics()
    assert "max_rss_bytes" in metrics
    assert isinstance(metrics["max_rss_bytes"], int)
    assert metrics["max_rss_bytes"] > 0


def test_get_memory_metrics_unit():
    metrics = _get_memory_metrics()
    # should be > 1MB for any python process
    assert metrics["max_rss_bytes"] > 1024 * 1024


def test_get_gpu_metrics_no_gpu():
    metrics = _get_gpu_metrics()
    assert isinstance(metrics, dict)


def test_dry_run_func_sends_metrics(dry_run_pipes):
    p = dry_run_pipes
    proc = p["ctx"].Process(
        target=dry_run_func,
        args=(
            EchoWorker,
            1,
            p["data_receiver"],
            p["result_sender"],
            True,
            p["shutdown_notify"],
            p["metrics_sender"],
        ),
        daemon=True,
    )
    proc.start()
    p["data_sender"].send({"x": 42})

    assert p["result_receiver"].poll(timeout=10)
    p["result_receiver"].recv_bytes()

    assert p["metrics_receiver"].poll(timeout=5)
    metrics = p["metrics_receiver"].recv()

    assert metrics["stage"] == "EchoWorker"
    assert metrics["cpu_time_seconds"] >= 0
    assert metrics["max_rss_bytes"] > 0

    p["shutdown_notify"].set()
    proc.join(timeout=5)


def test_dry_run_func_batch_worker(dry_run_pipes):
    p = dry_run_pipes
    proc = p["ctx"].Process(
        target=dry_run_func,
        args=(
            BatchEchoWorker,
            8,
            p["data_receiver"],
            p["result_sender"],
            True,
            p["shutdown_notify"],
            p["metrics_sender"],
        ),
        daemon=True,
    )
    proc.start()
    p["data_sender"].send({"x": 42})

    assert p["result_receiver"].poll(timeout=10)
    p["result_receiver"].recv_bytes()

    assert p["metrics_receiver"].poll(timeout=5)
    metrics = p["metrics_receiver"].recv()
    assert metrics["stage"] == "BatchEchoWorker"

    p["shutdown_notify"].set()
    proc.join(timeout=5)


def test_pool_collect_metrics(spawn_ctx):
    ctx, shutdown_notify = spawn_ctx

    pool = Pool(ctx, shutdown_notify)
    pool.new_pipe()

    runtime = Runtime(EchoWorker, num=1, max_batch_size=1, timeout=3.0)
    pool.start_worker(runtime, init=True)

    sender, receiver = pool.first_last_pipe()
    sender.send({"x": 1})

    assert receiver.poll(timeout=10)
    receiver.recv_bytes()

    metrics = pool.collect_metrics(timeout=5.0)
    assert len(metrics) == 1
    assert metrics[0]["stage"] == "EchoWorker"
    assert metrics[0]["cpu_time_seconds"] >= 0
    assert metrics[0]["max_rss_bytes"] > 0

    shutdown_notify.set()
    pool.wait_all()


def test_pool_collect_metrics_timeout(spawn_ctx):
    ctx, shutdown_notify = spawn_ctx
    pool = Pool(ctx, shutdown_notify)

    metrics = pool.collect_metrics(timeout=0.1)
    assert metrics == []
