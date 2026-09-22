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

"""MOSEC worker interface.

This module provides the interface to define a worker with such behaviors:

    1. initialize
    2. serialize/deserialize data to/from another worker
    3. serialize/deserialize data to/from the client side
    4. data processing
"""

from __future__ import annotations

import abc
import json
import logging
import pickle
from collections import defaultdict
from typing import TYPE_CHECKING, Any, Dict, List, Sequence, Tuple

from mosec.cache import SieveCache

from mosec.errors import DecodingError, EncodingError
from mosec.utils import ParseTarget

MOSEC_REF_TEMPLATE = "#/components/schemas/{name}"

if TYPE_CHECKING:
    from queue import SimpleQueue
    from threading import Semaphore


class Worker(abc.ABC):
    """MOSEC worker interface.

    It provides default IPC (de)serialization methods, stores the worker
    meta data including its stage and maximum batch size, and leaves the
    ``forward`` method to be implemented by the users.

    By default, we use `JSON <https://www.json.org/>`__ encoding. But users
    are free to customize via simply overriding the ``deserialize`` method
    in the **first** stage (we term it as *ingress* stage) and/or the
    ``serialize`` method in the **last** stage (we term it as *egress*
    stage).

    For the encoding customization, there are many choices including
    `MessagePack <https://msgpack.org/index.html>`__, `Protocol
    Buffer <https://developers.google.com/protocol-buffers>`__ and many
    other out-of-the-box protocols. Users can even define their own protocol
    and use it to manipulate the raw bytes! A naive customization can be
    found in this :doc:`PyTorch example </examples/pytorch>`.
    """

    # pylint: disable=no-self-use

    example: Any = None
    multi_examples: Sequence[Any] = []
    resp_mime_type = "application/json"
    _worker_id: int = 0
    _stage: str = ""
    _max_batch_size: int = 1

    def __init__(self):
        """Initialize the worker.

        This method doesn't require the child class to override.
        """
        super().__init__()

    def serialize_ipc(self, data: Any) -> bytes:
        """Define IPC serialization method.

        Args:
            data: returned data from :py:meth:`forward`

        """
        return pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL)

    def deserialize_ipc(self, data: bytes) -> Any:
        """Define IPC deserialization method.

        Args:
            data: input data for :py:meth:`forward`

        """
        return pickle.loads(data)

    @property
    def stage(self) -> str:
        """Return the stage name."""
        return self._stage

    @stage.setter
    def stage(self, stage):
        self._stage = stage

    @property
    def max_batch_size(self) -> int:
        """Return the maximum batch size."""
        return self._max_batch_size

    @max_batch_size.setter
    def max_batch_size(self, max_batch_size):
        self._max_batch_size = max_batch_size

    @property
    def worker_id(self) -> int:
        """Return the ID of this worker instance.

        This property returns the worker ID in the range of [1, ... , ``num``]
        (``num`` as configured in
        :py:meth:`append_worker(num) <mosec.server.Server.append_worker>`)
        to differentiate workers in the same stage.
        """
        return self._worker_id

    @worker_id.setter
    def worker_id(self, worker_id):
        self._worker_id = worker_id

    def serialize(self, data: Any) -> bytes:
        """Serialize the last stage (egress).

        Default response serialization method: JSON.

        Check :py:mod:`mosec.mixin` for more information.

        Arguments:
            data: the same type as the output of the :py:meth:`forward`

        Returns:
            the bytes you want to put into the response body

        Raises:
            EncodingError: if the data cannot be serialized with JSON

        """
        try:
            data_bytes = json.dumps(data, indent=2).encode()
        except Exception as err:
            raise EncodingError from err
        return data_bytes

    def deserialize(self, data: bytes) -> Any:
        """Deserialize the first stage (ingress).

        Default request deserialization method: JSON.

        Check :py:mod:`mosec.mixin` for more information.

        Arguments:
            data: the raw bytes extracted from the request body

        Returns:
            the same type as the input of the :py:meth:`forward`

        Raises:
            DecodingError: if the data cannot be deserialized with JSON

        """
        try:
            data_json = json.loads(data) if data else {}
        except Exception as err:
            raise DecodingError from err
        return data_json

    @abc.abstractmethod
    def forward(self, data: Any) -> Any:
        """Model inference, data processing or computation logic.

        Args:
            data: input data to be processed

        **Must be overridden** by the subclass.

        If any code in this :py:meth:`forward` needs to access other resources (e.g.
        a model, a memory cache, etc.), the user should initialize these resources
        as attributes of the class in the :py:class:`__init__ <mosec.worker.Worker>`.

        .. note::

            For a stage that enables dynamic batching, please return the results
            that have the same length and the same order of the input data.

        .. note::

            - for a single-stage worker, data will go through
                ``<deserialize> -> <forward> -> <serialize>``

            - for a multi-stage worker that is neither `ingress` not `egress`, data
                will go through ``<deserialize_ipc> -> <forward> -> <serialize_ipc>``

        """
        raise NotImplementedError

    @classmethod
    def get_forward_json_schema(
        cls,
        target: ParseTarget,
        ref_template: str,  # pylint: disable=unused-argument
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Retrieve the JSON schema for the `forward` method of the class.

        Args:
            cls : The class object.
            target : The target variable to parse the schema for.
            ref_template : A template to use when generating ``"$ref"`` fields.

        Returns:
            A tuple containing the schema and the component schemas.

        The :py:meth:`get_forward_json_schema` method is a class method that returns the
        JSON schema for the :py:meth:`forward` method of the :py:class:`cls` class.
        It takes a :py:obj:`target` param specifying the target to parse the schema for.

        The returned value is a tuple containing the schema and the component schema.

        .. note::

            Developer must implement this function to retrieve the JSON schema
            to enable openapi spec.

        .. note::

            The :py:const:`MOSEC_REF_TEMPLATE` constant should be used as a reference
            template according to openapi standards.

        """
        return {}, {}


class SSEWorker(Worker):
    """MOSEC worker with Server-Sent Events (SSE) support."""

    _stream_queue: SimpleQueue
    _stream_semaphore: Semaphore
    resp_mime_type = "text/event-stream"

    def send_stream_event(self, text: str, index: int = 0):
        """Send a stream event to the client.

        Args:
            text: the text to be sent, needs to be UTF-8 compatible
            index: the index of the stream event. For the single request, this will
                always be 0. For dynamic batch request, this should be the index of
                the request in this batch.

        """
        if self._stream_queue is None or self._stream_semaphore is None:
            raise RuntimeError("the worker stream or semaphore is not initialized")
        self._stream_semaphore.acquire()
        self._stream_queue.put((text, index))


class MultiModelWorker(Worker):
    """MOSEC worker with dynamic multi-model loading and SIEVE cache eviction.

    It maintains a fixed-size cache of loaded models and implements
    ``forward`` by grouping each batch into per-``model_id`` sub-batches.
    Missing models are loaded on demand; when the cache is full the SIEVE
    policy evicts an entry to make room.

    The user must override ``load_model`` and ``forward_model``.
    Optionally override ``unload_model`` to clean up evicted models, or
    ``get_model_id`` to change how the model identifier is extracted from
    each request item (default: ``item["model_id"]``).

    The eviction policy is SIEVE (Zhang et al., NSDI '24) — a single queue
    with one pointer and one bit per entry, no reordering on cache hit.
    See https://sievecache.com for details.
    """

    max_cache_size: int = 5
    """Maximum number of models to keep loaded simultaneously."""

    def __init__(self):
        """Initialize the worker and its model cache."""
        super().__init__()
        self._model_cache: SieveCache[str, Any] = SieveCache(self.max_cache_size)
        self._logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @abc.abstractmethod
    def load_model(self, model_id: str) -> Any:
        """Load and return a model object for the given identifier.

        Called on a cache miss. The returned object is stored in the cache
        and passed to ``forward_model`` on subsequent hits.

        Args:
            model_id: identifier of the model to load.

        Returns:
            The loaded model (any type).
        """
        raise NotImplementedError

    def unload_model(self, model_id: str, model: Any) -> None:
        """Clean up a model that was just evicted from the cache.

        Override this to free GPU memory, close file handles, etc.
        The default implementation does nothing.

        Args:
            model_id: identifier of the evicted model.
            model: the model object that was evicted.
        """
        pass

    @abc.abstractmethod
    def forward_model(
        self, model_id: str, model: Any, data: List[Any]
    ) -> List[Any]:
        """Run inference on a sub-batch for a single model.

        Args:
            model_id: identifier of the model.
            model: the loaded model object (as returned by ``load_model``).
            data: list of request items that share this ``model_id``.

        Returns:
            A list of results, same length and same order as *data*.
        """
        raise NotImplementedError

    def get_model_id(self, item: Any) -> str:
        """Extract the model identifier from a request item.

        The default expects *item* to be a dict with a ``"model_id"`` key.
        Override this if your items use a different structure.

        Args:
            item: one element from the batch.

        Returns:
            The model identifier string.
        """
        return item["model_id"]

    def forward(self, data: Any) -> Any:
        """Group the batch by model_id, manage the cache, dispatch sub-batches.

        This method is sealed. Override ``forward_model`` instead.
        """
        is_batched = self.max_batch_size > 1
        items: List[Any] = data if is_batched else [data]

        groups: Dict[str, List[Tuple[int, Any]]] = defaultdict(list)
        for idx, item in enumerate(items):
            mid = self.get_model_id(item)
            groups[mid].append((idx, item))

        # Process cache-hit groups before cache-miss groups so that hits
        # are never blocked behind a slow model load.
        hit_groups = []
        miss_groups = []
        for model_id, indexed_items in groups.items():
            if model_id in self._model_cache:
                hit_groups.append((model_id, indexed_items))
            else:
                miss_groups.append((model_id, indexed_items))

        results: List[Any] = [None] * len(items)
        for model_id, indexed_items in hit_groups + miss_groups:
            model = self._ensure_model(model_id)
            sub_data = [item for _, item in indexed_items]
            sub_results = self.forward_model(model_id, model, sub_data)
            for (orig_idx, _), result in zip(indexed_items, sub_results):
                results[orig_idx] = result

        return results if is_batched else results[0]

    def _ensure_model(self, model_id: str) -> Any:
        """Return the model for *model_id*, loading on cache miss."""
        model = self._model_cache.get(model_id)
        if model is not None:
            return model

        self._logger.info("cache miss for model_id=%r, loading", model_id)

        if len(self._model_cache) >= self._model_cache.max_size:
            evicted = self._model_cache.evict()
            if evicted is not None:
                evicted_key, evicted_model = evicted
                self._logger.info(
                    "evicting model_id=%r to make room for %r",
                    evicted_key,
                    model_id,
                )
                self.unload_model(evicted_key, evicted_model)

        model = self.load_model(model_id)
        self._model_cache.put(model_id, model)
        return model

