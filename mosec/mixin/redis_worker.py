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

"""MOSEC redis worker mixin.

Provide another data transfer way between workers.

The data will be stored in redis shared memory, while the object ID will be
sent via the original way.

    use case: large image tensors, cluster-shared data
    benefits: more stable P99 latency

"""
import warnings
from os import environ
from typing import Any

try:
    import redis  # type: ignore
except ImportError:
    warnings.warn(
        "redis is not installed. RedisShmIPCMixin is not available.", ImportWarning
    )


from mosec.worker import Worker

_REDIS_URL_ENV = "MOSEC_INTERNAL_REDIS_URL"
_DEFAULT_KEY = "REDIS_SHM_IPC_KEY"


class RedisShmIPCMixin(Worker):
    """Redis shared memory worker mixin interface."""

    # pylint: disable=no-self-use

    _redis_client = None
    _redis_key = _DEFAULT_KEY
    _next_id = None

    @classmethod
    def set_redis_url(cls, url: str):
        """Set the redis service url."""
        environ[_REDIS_URL_ENV] = url

    def _get_client(self) -> Any:
        """Get the redis client. This will create a new one if not exist."""
        if self._redis_client is None:
            url = environ.get(_REDIS_URL_ENV)
            if not url:
                raise RuntimeError(
                    "please set the redis url with "
                    "`RedisShmIPCMixin.set_redis_url()`"
                )
            self._redis_client = redis.from_url(url)
        return self._redis_client

    def _prepare_next_id(self) -> None:
        """Make sure the next id exists. This will create a new one if not exist."""
        if self._next_id is None:
            client = self._get_client()
            key = self._redis_key
            self._next_id = bytes(str(client.incr(key)), encoding="utf-8")

    def serialize_ipc(self, data: Any) -> bytes:
        """Save the data to the redis server and return the id."""
        self._prepare_next_id()
        client = self._get_client()
        with client.pipeline() as pipe:
            current_id = self._next_id
            pipe.set(current_id, super().serialize_ipc(data))  # type: ignore
            pipe.incr(self._redis_key)
            _id = pipe.execute()[-1]
            self._next_id = bytes(str(_id), encoding="utf-8")
        return current_id  # type: ignore

    def deserialize_ipc(self, data: bytes) -> Any:
        """Get the data from the redis server and delete it."""
        client = self._get_client()
        object_id = bytes(data)
        with client.pipeline() as pipe:
            pipe.get(object_id)
            pipe.delete(object_id)
            obj = pipe.execute()[0]
        return super().deserialize_ipc(obj)
