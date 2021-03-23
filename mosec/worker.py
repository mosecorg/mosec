import json
import pickle

from pydantic.json import pydantic_encoder


class Worker:
    """
    This public class defines the mosec worker interface. It provides
    default IPC de/serialize methods, stores the worker stage and
    maximum batch size, and implements the forward pass pipeline.
    """

    def __init__(self):
        self._stage = None
        self._max_batch_size = 1

    @staticmethod
    def _serialize_ipc(data):
        """Define IPC serialize method"""
        return pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL)

    @staticmethod
    def _deserialize_ipc(data):
        """Define IPC deserialize method"""
        return pickle.loads(data)

    def _set_stage(self, stage):
        self._stage = stage

    def _set_mbs(self, mbs):
        self._max_batch_size = mbs

    @staticmethod
    def deserialize(data):
        """Define service ingress unpack method, overridable"""
        return json.loads(data) if data else {}

    @staticmethod
    def serialize(data):
        """Define service egress pack method, overridable"""
        return json.dumps(data, indent=2, default=pydantic_encoder).encode()

    def forward(self):
        """Define worker's computation, must be overridden by all subclasses"""
        raise NotImplementedError
