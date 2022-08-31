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

import abc
import json
import logging
import pickle
from typing import Any

from .errors import DecodingError, EncodingError

logger = logging.getLogger(__name__)


class Worker(abc.ABC):
    """MOSEC worker interface.

    It provides default IPC (de)serialization methods, stores the worker meta data
    including its stage and maximum batch size, and leaves the `forward` method to
    be implemented by the users.

    By default, we use [JSON](https://www.json.org/) encoding. But users
    are free to customize via simply overridding the `deserialize` method
    in the **first** stage (we term it as _ingress_ stage) and/or
    the `serialize` method in the **last** stage (we term it as _egress_ stage).

    For the encoding customization, there are many choices including
    [MessagePack](https://msgpack.org/index.html),
    [Protocol Buffer](https://developers.google.com/protocol-buffers)
    and many other out-of-the-box protocols. Users can even define their own
    protocol and use it to manipulate the raw bytes!
    A naive customization can be found in [this
    example](https://mosecorg.github.io/mosec/example/pytorch/#sentiment-analysis).

    ###### Note
    > The "_same type_" mentioned below is applicable only when the stage
    disables batching. For a stage that
    [enables batching][mosec.server.Server--batching], the `worker`'s
    `forward` should accept a list and output a list, where each element
    will follow the "_same type_" constraint.
    """

    # pylint: disable=no-self-use

    example: Any = None
    _worker_id: int = 0

    def __init__(self):
        """Initialize the worker."""
        self._stage: str = ""
        self._max_batch_size: int = 1

    def serialize_ipc(self, data) -> bytes:
        """Define IPC serialize method."""
        return pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL)

    def deserialize_ipc(self, data) -> Any:
        """Define IPC deserialize method."""
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
        """Return the id of this worker instance.

        This property returns the worker id in the range of [1, ... ,`num`]
        (`num` as defined [here][mosec.server.Server--multiprocess])
        to differentiate workers in the same stage.
        """
        return self._worker_id

    @worker_id.setter
    def worker_id(self, worker_id):
        self._worker_id = worker_id

    def serialize(self, data: Any) -> bytes:
        """Serialize method for the last stage (egress).

        No need to override this method by default, but overridable.

        Arguments:
            data: the [_*same type_][mosec.worker.Worker--note] as the
                output of the `forward` you implement

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
        """Deserialize method for the first stage (ingress).

        No need to override this method by default, but overridable.

        Arguments:
            data: the raw bytes extracted from the request body

        Returns:
            the [_*same type_][mosec.worker.Worker--note] as the argument of
            the `forward` you implement

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

        __Must be overridden__ by the subclass.
        The implementation should make sure:

        - (for a single-stage worker)
            - both the input and output follow the
            [_*same type_][mosec.worker.Worker--note] rule.
        - (for a multi-stage worker)
            - the input of the _ingress_ stage and the output of the _egress_
            stage follow the [_*same type_][mosec.worker.Worker--note], while
            others should align with its adjacent stage's in/output.

        If any code in the `forward` needs to access other resources (e.g. a model,
        a memory cache, etc.), the user should initialize these resources to be
        attributes of the class in the `__init__` method.
        """
        raise NotImplementedError
