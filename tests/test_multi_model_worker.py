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

"""Test MultiModelWorker sub-batching and cache management."""

from typing import Any, Dict, List

import pytest

from mosec.worker import MultiModelWorker


#  concrete test double 


class DummyMultiModelWorker(MultiModelWorker):
    """Minimal concrete implementation for testing."""

    max_cache_size = 3

    def __init__(self):
        super().__init__()
        self.loaded: Dict[str, str] = {}
        self.unloaded: List[str] = []
        self.load_count: int = 0

    def load_model(self, model_id: str) -> str:
        self.load_count += 1
        obj = f"model_{model_id}"
        self.loaded[model_id] = obj
        return obj

    def unload_model(self, model_id: str, model: Any) -> None:
        self.unloaded.append(model_id)

    def forward_model(
        self, model_id: str, model: Any, data: List[Any]
    ) -> List[Any]:
        return [
            {"model_id": model_id, "model_obj": model, "input": d}
            for d in data
        ]


@pytest.fixture
def worker():
    """Batched worker with cache size 3."""
    DummyMultiModelWorker.max_cache_size = 3
    w = DummyMultiModelWorker()
    w.max_batch_size = 8
    return w


@pytest.fixture
def small_cache_worker():
    """Batched worker with cache size 2."""
    DummyMultiModelWorker.max_cache_size = 2
    w = DummyMultiModelWorker()
    w.max_batch_size = 8
    return w


#  sub-batching and ordering 


def test_single_model_id(worker):
    batch = [{"model_id": "A", "x": i} for i in range(4)]
    results = worker.forward(batch)
    assert len(results) == 4
    assert all(r["model_id"] == "A" for r in results)


def test_multiple_model_ids_preserve_order(worker):
    batch = [
        {"model_id": "A", "idx": 0},
        {"model_id": "B", "idx": 1},
        {"model_id": "A", "idx": 2},
        {"model_id": "C", "idx": 3},
        {"model_id": "B", "idx": 4},
    ]
    results = worker.forward(batch)
    assert len(results) == 5
    for inp, out in zip(batch, results):
        assert out["model_id"] == inp["model_id"]
        assert out["input"] == inp


def test_single_item_mode():
    """When max_batch_size == 1, forward receives a single item, not a list."""
    DummyMultiModelWorker.max_cache_size = 3
    w = DummyMultiModelWorker()
    w.max_batch_size = 1
    item = {"model_id": "X", "value": 42}
    result = w.forward(item)
    assert isinstance(result, dict)
    assert result["model_id"] == "X"
    assert result["input"] == item


#  cache hit / miss 


def test_cache_hit_does_not_reload(worker):
    worker.forward([{"model_id": "A", "v": 1}])
    worker.forward([{"model_id": "A", "v": 2}])
    assert worker.load_count == 1


def test_cache_miss_triggers_load(worker):
    worker.forward([{"model_id": "A"}])
    worker.forward([{"model_id": "B"}])
    worker.forward([{"model_id": "C"}])
    assert worker.load_count == 3


def test_eviction_triggers_unload(small_cache_worker):
    w = small_cache_worker
    w.forward([{"model_id": "A"}])
    w.forward([{"model_id": "B"}])
    assert len(w.unloaded) == 0
    w.forward([{"model_id": "C"}])
    assert len(w.unloaded) == 1


def test_eviction_unloads_correct_model(small_cache_worker):
    w = small_cache_worker
    w.forward([{"model_id": "A"}])
    w.forward([{"model_id": "B"}])
    w.forward([{"model_id": "B"}])  # mark "B" as visited
    w.forward([{"model_id": "C"}])  # should evict "A", not "B"
    assert "A" in w.unloaded
    assert "B" not in w.unloaded


#  custom get_model_id 


def test_override_get_model_id():
    class CustomIdWorker(DummyMultiModelWorker):
        def get_model_id(self, item):
            return item["variant"]

    CustomIdWorker.max_cache_size = 3
    w = CustomIdWorker()
    w.max_batch_size = 4
    batch = [
        {"variant": "v1", "data": "a"},
        {"variant": "v2", "data": "b"},
    ]
    results = w.forward(batch)
    assert results[0]["model_id"] == "v1"
    assert results[1]["model_id"] == "v2"


#  edge cases 


@pytest.mark.parametrize("batch_size", [1, 5, 10])
def test_batch_all_same_model(batch_size, worker):
    batch = [{"model_id": "only"} for _ in range(batch_size)]
    results = worker.forward(batch)
    assert len(results) == batch_size
    assert worker.load_count == 1


def test_many_models_cycle_through_cache(small_cache_worker):
    """Cycling through more models than cache size works without errors."""
    w = small_cache_worker
    for i in range(20):
        w.forward([{"model_id": f"model_{i}"}])
    assert w.load_count == 20
    assert len(w.unloaded) == 18  # 20 loads - 2 cache slots


def test_cache_hits_processed_before_misses(worker):
    """Cache-hit groups must not be blocked behind cache-miss groups.

    Even if a miss model_id appears first in the batch, the hit groups
    should be dispatched to forward_model first.
    """
    # Pre-load "A" into the cache.
    worker.forward([{"model_id": "A"}])

    # Track the order forward_model is called per model_id.
    call_order = []
    orig_forward_model = worker.forward_model

    def tracking_forward_model(model_id, model, data):
        call_order.append(model_id)
        return orig_forward_model(model_id, model, data)

    worker.forward_model = tracking_forward_model

    # "B" (miss) appears before "A" (hit) in the batch.
    batch = [
        {"model_id": "B", "v": 1},
        {"model_id": "A", "v": 2},
    ]
    results = worker.forward(batch)

    # "A" (hit) should have been processed before "B" (miss).
    assert call_order == ["A", "B"]
    # Results are still in the original request order.
    assert results[0]["model_id"] == "B"
    assert results[1]["model_id"] == "A"
