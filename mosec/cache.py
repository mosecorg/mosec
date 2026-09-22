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

"""SIEVE cache eviction algorithm (NSDI '24).

A cache that is simpler than LRU and achieves a better miss ratio.
One doubly-linked list, one persistent "hand" pointer, one visited-bit
per entry.

On access (cache hit): set the visited bit. Nothing moves.
On evict: walk from the hand toward the head. For each node whose bit
is set, clear it and advance. Evict the first node whose bit is already
clear. The hand stays where it stopped so the next eviction resumes
from there.

This implementation is not thread-safe. In mosec it is only accessed
from within a single worker process's synchronous ``forward()`` call,
so no locking is needed.

Reference:
    Yazhuo Zhang, Juncheng Yang, Yao Yue, Ymir Vigfusson, K. V. Rashmi.
    "SIEVE is Simpler than LRU: an Efficient Turn-Key Eviction Algorithm
    for Web Caches." NSDI '24. https://sievecache.com
"""

from __future__ import annotations

from typing import Dict, Generic, List, Optional, Tuple, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class _Node(Generic[K, V]):
    """Doubly-linked list node with a visited bit."""

    __slots__ = ("key", "value", "visited", "prev", "next")

    def __init__(self, key: K, value: V) -> None:
        self.key = key
        self.value = value
        self.visited: bool = False
        self.prev: Optional[_Node[K, V]] = None
        self.next: Optional[_Node[K, V]] = None


class SieveCache(Generic[K, V]):
    """Fixed-capacity cache with SIEVE eviction.

    The cache is built on a doubly-linked list (head = newest, tail = oldest)
    and a hash map for O(1) lookup. A persistent ``hand`` pointer sweeps
    from tail toward head during eviction, giving visited nodes a second
    chance before evicting unvisited ones.

    Args:
        max_size: maximum number of entries the cache may hold. Must be >= 1.
    """

    def __init__(self, max_size: int) -> None:
        if max_size < 1:
            raise ValueError(f"max_size must be >= 1, got {max_size}")
        self._max_size = max_size
        self._map: Dict[K, _Node[K, V]] = {}
        self._head: Optional[_Node[K, V]] = None
        self._tail: Optional[_Node[K, V]] = None
        self._hand: Optional[_Node[K, V]] = None

    @property
    def max_size(self) -> int:
        """Return the maximum capacity."""
        return self._max_size

    def __len__(self) -> int:
        return len(self._map)

    def __contains__(self, key: K) -> bool:
        return key in self._map

    def get(self, key: K) -> Optional[V]:
        """Look up *key*. On hit, set the visited bit and return the value.

        Returns ``None`` on a cache miss.
        """
        node = self._map.get(key)
        if node is None:
            return None
        node.visited = True
        return node.value

    def put(self, key: K, value: V) -> Optional[Tuple[K, V]]:
        """Insert or update *key*.

        If the key already exists its value is replaced in place (no
        eviction, no repositioning -- this matches SIEVE semantics where
        only the visited bit changes on access, unlike LRU).

        If the cache is full a single entry is evicted via SIEVE.

        Returns:
            ``(evicted_key, evicted_value)`` if an eviction happened,
            ``None`` otherwise.
        """
        node = self._map.get(key)
        if node is not None:
            node.value = value
            node.visited = True
            return None

        evicted: Optional[Tuple[K, V]] = None
        if len(self._map) >= self._max_size:
            evicted = self._evict()

        new_node = _Node(key, value)
        self._push_head(new_node)
        self._map[key] = new_node
        return evicted

    def remove(self, key: K) -> Optional[V]:
        """Remove *key* explicitly, bypassing the eviction policy.

        Useful for invalidating a stale model version. Returns the value
        if the key was present, ``None`` otherwise.
        """
        node = self._map.pop(key, None)
        if node is None:
            return None
        self._remove(node)
        return node.value

    def evict(self) -> Optional[Tuple[K, V]]:
        """Manually evict one entry via SIEVE.

        Returns:
            ``(evicted_key, evicted_value)`` or ``None`` if empty.
        """
        if not self._map:
            return None
        return self._evict()

    def _evict(self) -> Optional[Tuple[K, V]]:
        """Core SIEVE eviction with a persistent hand.

        The hand walks from its current position toward the head:
        visited nodes get their bit cleared (second chance), unvisited
        nodes are evicted. If the hand reaches the head without finding
        an unvisited node it wraps back to the tail and continues.

        Uses an iterative loop instead of recursion so it cannot hit
        Python's recursion limit even with a large, fully-visited cache.
        """
        if not self._map:
            return None

        if self._hand is None:
            self._hand = self._tail

        while True:
            victim = self._hand
            while victim is not None:
                if victim.visited:
                    victim.visited = False
                    victim = victim.prev
                else:
                    self._hand = victim.prev
                    self._remove(victim)
                    del self._map[victim.key]
                    return (victim.key, victim.value)
            # All visited bits were cleared in one pass. Wrap to tail
            # and scan again -- this time at least one node is unvisited.
            self._hand = self._tail

    def _push_head(self, node: _Node[K, V]) -> None:
        """Insert *node* at the head of the list."""
        node.prev = None
        node.next = self._head
        if self._head is not None:
            self._head.prev = node
        self._head = node
        if self._tail is None:
            self._tail = node

    def _remove(self, node: _Node[K, V]) -> None:
        """Unlink *node* from the list."""
        if node.prev is not None:
            node.prev.next = node.next
        else:
            self._head = node.next

        if node.next is not None:
            node.next.prev = node.prev
        else:
            self._tail = node.prev

        if self._hand is node:
            self._hand = node.prev

        node.prev = None
        node.next = None

    def keys(self) -> List[K]:
        """Return cached keys in order from head (newest) to tail (oldest)."""
        result: List[K] = []
        node = self._head
        while node is not None:
            result.append(node.key)
            node = node.next
        return result

    def items(self) -> List[Tuple[K, V]]:
        """Return cached (key, value) pairs, head to tail."""
        result: List[Tuple[K, V]] = []
        node = self._head
        while node is not None:
            result.append((node.key, node.value))
            node = node.next
        return result
