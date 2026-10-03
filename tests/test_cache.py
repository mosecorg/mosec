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

"""Test SIEVE cache eviction logic."""

import pytest

from mosec.cache import SieveCache


@pytest.fixture
def cache():
    return SieveCache(3)


@pytest.fixture
def full_cache():
    c = SieveCache(3)
    c.put("a", 1)
    c.put("b", 2)
    c.put("c", 3)
    return c


# basic operations

def test_put_and_get(cache):
    cache.put("a", 1)
    assert cache.get("a") == 1


def test_get_miss_returns_none(cache):
    assert cache.get("missing") is None


def test_len(cache):
    assert len(cache) == 0
    cache.put("a", 1)
    cache.put("b", 2)
    assert len(cache) == 2


def test_contains(cache):
    cache.put("x", 10)
    assert "x" in cache
    assert "y" not in cache


def test_keys_head_to_tail(cache):
    for k in ("a", "b", "c"):
        cache.put(k, ord(k))
    assert cache.keys() == ["c", "b", "a"]


def test_update_existing_key(cache):
    cache.put("a", 1)
    evicted = cache.put("a", 99)
    assert evicted is None
    assert cache.get("a") == 99
    assert len(cache) == 1


#eviction semantics 

def test_eviction_returns_key_value():
    c = SieveCache(2)
    c.put("a", 1)
    c.put("b", 2)
    evicted = c.put("c", 3)
    assert evicted is not None
    assert evicted[0] in ("a", "b")


def test_unvisited_evicted_first():
    c = SieveCache(2)
    c.put("a", "model_a")
    c.put("b", "model_b")
    c.get("a")  # mark "a" as visited
    evicted = c.put("c", "model_c")
    assert evicted == ("b", "model_b")
    assert "a" in c
    assert "c" in c


def test_visited_gets_second_chance():
    c = SieveCache(2)
    c.put("a", 1)
    c.put("b", 2)
    c.get("a")
    c.get("b")
    # both visited — first pass clears bits, second pass evicts the tail
    evicted = c.put("c", 3)
    assert evicted is not None
    assert evicted[0] == "a"


def test_persistent_hand_across_evictions(full_cache):
    """Hand survives across eviction calls instead of resetting to tail."""
    evicted1 = full_cache.put("d", 4)
    assert evicted1 == ("a", 1)
    evicted2 = full_cache.put("e", 5)
    assert evicted2 == ("b", 2)


def test_manual_evict(full_cache):
    result = full_cache.evict()
    assert result is not None
    assert len(full_cache) == 2


def test_evict_empty(cache):
    assert cache.evict() is None


def test_size_one():
    c = SieveCache(1)
    c.put("a", "first")
    evicted = c.put("b", "second")
    assert evicted == ("a", "first")
    assert c.get("b") == "second"
    assert c.get("a") is None


def test_all_visited_then_evict(full_cache):
    full_cache.get("a")
    full_cache.get("b")
    full_cache.get("c")
    evicted = full_cache.evict()
    assert evicted is not None
    assert len(full_cache) == 2


# capacity  


def test_invalid_max_size():
    with pytest.raises(ValueError, match="max_size must be >= 1"):
        SieveCache(0)


@pytest.mark.parametrize("n_inserts", [10, 50, 100])
def test_never_exceeds_max_size(n_inserts):
    c = SieveCache(3)
    for i in range(n_inserts):
        c.put(f"key_{i}", i)
    assert len(c) <= 3


# helpers

def test_items(cache):
    cache.put("x", 10)
    cache.put("y", 20)
    items = cache.items()
    assert ("y", 20) in items
    assert ("x", 10) in items


def test_keys(cache):
    cache.put("a", 1)
    cache.put("b", 2)
    assert cache.keys() == ["b", "a"]


# explicit removal

def test_remove_existing(cache):
    cache.put("a", 1)
    cache.put("b", 2)
    val = cache.remove("a")
    assert val == 1
    assert "a" not in cache
    assert len(cache) == 1


def test_remove_missing(cache):
    assert cache.remove("nope") is None


def test_remove_does_not_break_eviction():
    c = SieveCache(3)
    c.put("a", 1)
    c.put("b", 2)
    c.put("c", 3)
    c.remove("b")
    # cache has 2 entries now, inserting should not evict
    evicted = c.put("d", 4)
    assert evicted is None
    assert len(c) == 3
