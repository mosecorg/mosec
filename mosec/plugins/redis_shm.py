# Copyright 2023 MOSEC Authors
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

"""Provide another data transfer way between workers.

The data will be stored in redis shared memory, while the id will be
sent via the original way.

    use case: large image tensors, cluster-shared data
    benefits: more stable P99 latency, consistency
"""

from functools import partial
from typing import Callable, List, Union

import redis

from mosec.ipc import IPCWrapper

DEFAULT_KEY = "redis-shm"


class RedisShmWrapper(IPCWrapper):
    """Shared memory wrapper using Redis.

    This class is an implementation of the IPCWrapper interface that uses Redis
    as the in-memory data store for efficient data transfer.
    """

    def __init__(
        self,
        url: str = "",
        id_gen: Union[None, Callable[[], bytes]] = None,
    ) -> None:
        """Initialize the IPC Wrapper with a Redis client.

        Since unix socket performs better than TCP socket, it is recommended to use.

        Args:
            url (str): Redis server connect url, could be tcp/unix socket url.
            id_gen (Callable[[], bytes]): Redis id generator.
        """
        self.client = redis.from_url(url)

        if not id_gen:

            def int_to_bytes(number: int) -> bytes:
                return str(number).encode()

            def bytes_id_gen() -> bytes:
                int_id_gen = partial(self.client.incr, DEFAULT_KEY)
                return int_to_bytes(int_id_gen())

            id_gen = bytes_id_gen

        self.id_gen = id_gen

    def _put_single(self, data: bytes) -> bytes:
        _id = self.id_gen()
        self.client.set(_id, data)
        return _id

    def _put_redis(self, data: List[bytes]) -> List[bytes]:
        """Batch put data into Redis."""
        return [self._put_single(item) for item in data]

    def _get_redis(self, ids: List[bytes]) -> List[bytes]:
        """Batch get data from Redis."""
        return [self.client.get(id) or bytes() for id in ids]

    def put(self, data: List[bytes]) -> List[bytes]:
        """Save data to Redis and return the ids."""
        return self._put_redis(data)

    def get(self, ids: List[bytes]) -> List[bytes]:
        """Get data from Redis by ids."""
        return self._get_redis(ids)
