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

import sys
from multiprocessing.context import SpawnContext
from types import SimpleNamespace
from typing import List

import pytest

from mosec.dry_run import (
    Pool,
    _get_gpu_metrics,
    _get_memory_metrics,
    _get_nvml_handle,
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


class FakeNVML:
    def __init__(self, count=2, pci_ok=True):
        self.count = count
        self.pci_ok = pci_ok

    def nvmlDeviceGetCount(self):
        return self.count

    def nvmlDeviceGetHandleByUUID(self, uuid):
        return ("uuid", uuid)

    def nvmlDeviceGetHandleByPciBusId(self, bus_id):
        if not self.pci_ok:
            raise RuntimeError("NVML_ERROR_NOT_FOUND")
        return ("pci", bus_id)

    def nvmlDeviceGetHandleByIndex(self, index):
        return ("index", index)


def fake_torch(available=True, **prop):
    return SimpleNamespace(
        cuda=SimpleNamespace(
            is_available=lambda: available,
            current_device=lambda: 0,
            get_device_properties=lambda _: SimpleNamespace(**prop),
        )
    )


TORCH_2_8 = fake_torch(pci_domain_id=0, pci_bus_id=0x41, pci_device_id=0, uuid="ab-cd")
TORCH_2_5 = fake_torch(uuid="ab-cd")
TORCH_2_4 = fake_torch()
NO_CUDA = fake_torch(available=False)


@pytest.mark.parametrize(
    "visible, order, torch, nvml, expected",
    [
        (None, None, TORCH_2_8, FakeNVML(), ("pci", b"00000000:41:00.0")),
        ("3,1", None, TORCH_2_8, FakeNVML(), ("pci", b"00000000:41:00.0")),
        ("3,1", None, TORCH_2_5, FakeNVML(), ("uuid", b"GPU-ab-cd")),
        ("GPU-abc,1", None, TORCH_2_8, FakeNVML(), ("uuid", b"GPU-abc")),
        ("MIG-abc", None, None, FakeNVML(), ("uuid", b"MIG-abc")),
        ("3,1", "PCI_BUS_ID", None, FakeNVML(), ("index", 3)),
        ("3,1", "PCI_BUS_ID", NO_CUDA, FakeNVML(), ("index", 3)),
        # a single GPU cannot be mixed up
        (None, None, None, FakeNVML(count=1), ("index", 0)),
        (None, None, TORCH_2_4, FakeNVML(count=1), ("index", 0)),
        (None, None, TORCH_2_8, FakeNVML(count=1, pci_ok=False), ("index", 0)),
        # a CUDA index in fastest-first order may not be the NVML index
        ("3,1", None, None, FakeNVML(), None),
        (None, None, NO_CUDA, FakeNVML(), None),
        (None, None, TORCH_2_4, FakeNVML(), None),
        (None, None, TORCH_2_8, FakeNVML(pci_ok=False), None),
        ("", None, TORCH_2_8, FakeNVML(), None),
    ],
)
def test_get_nvml_handle(monkeypatch, visible, order, torch, nvml, expected):
    for key, value in (("CUDA_VISIBLE_DEVICES", visible), ("CUDA_DEVICE_ORDER", order)):
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    # a None entry in sys.modules makes `import torch` raise ImportError
    monkeypatch.setitem(sys.modules, "torch", torch)
    assert _get_nvml_handle(nvml) == expected


def test_dry_run_func_sends_metrics(dry_run_pipes):
    p = dry_run_pipes
    proc = p["ctx"].Process(
        target=dry_run_func,
        args=(
            EchoWorker,
            "echo_stage",
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

    assert metrics["stage"] == "echo_stage"
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
            "batch_stage",
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
    assert metrics["stage"] == "batch_stage"

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
    assert metrics[0]["stage"] == "EchoWorker_1"
    assert metrics[0]["cpu_time_seconds"] >= 0
    assert metrics[0]["max_rss_bytes"] > 0

    shutdown_notify.set()
    pool.wait_all()


def test_pool_collect_metrics_timeout(spawn_ctx):
    ctx, shutdown_notify = spawn_ctx
    pool = Pool(ctx, shutdown_notify)

    metrics = pool.collect_metrics(timeout=0.1)
    assert metrics == []
