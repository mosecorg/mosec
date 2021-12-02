import abc
import json
import logging
import pickle
from typing import Any

from .errors import DecodingError

logger = logging.getLogger(__name__)


class Worker(abc.ABC):
    """
    This public class defines the mosec worker interface. It provides
    default IPC (de)serialization methods, stores the worker meta data
    including its stage and maximum batch size, and leaves the `forward`
    method to be implemented by the users.

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

    example: Any = None
    _id: int = 0

    def __init__(self):
        self._stage = None
        self._max_batch_size = 1

    def _serialize_ipc(self, data):
        """Define IPC serialize method"""
        return pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL)

    def _deserialize_ipc(self, data):
        """Define IPC deserialize method"""
        return pickle.loads(data)

    def _set_stage(self, stage):
        self._stage = stage

    def _set_mbs(self, mbs):
        self._max_batch_size = mbs

    @property
    def id(self) -> int:
        """
        This property returns the worker id in the range of [1, ... ,`num`]
        (`num` as defined [here][mosec.server.Server--multiprocess])
        to differentiate workers in the same stage.
        """
        return self._id

    def serialize(self, data: Any) -> bytes:
        """
        This method defines serialization of the last stage (egress).
        No need to override this method by default, but overridable.

        Arguments:
            data: the [_*same type_][mosec.worker.Worker--note] as the
                output of the `forward` you implement

        Returns:
            the bytes you want to put into the response body
        """
        try:
            data_bytes = json.dumps(data, indent=2).encode()
        except Exception as err:
            raise ValueError(err)
        return data_bytes

    def deserialize(self, data: bytes) -> Any:
        """
        This method defines the deserialization of the first stage (ingress).
        No need to override this method by default, but overridable.

        Arguments:
            data: the raw bytes extracted from the request body

        Returns:
            the [_*same type_][mosec.worker.Worker--note] as the argument of
            the `forward` you implement
        """
        try:
            data_json = json.loads(data) if data else {}
        except Exception as err:
            raise DecodingError(err)
        return data_json

    @abc.abstractmethod
    def forward(self, data: Any) -> Any:
        """
        This method defines the worker's main logic, be it data processing,
        computation or model inference. __Must be overridden__ by the subclass.
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
