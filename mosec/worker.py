import json
import pickle


class Worker:
    """
    This public class defines the mosec worker interface. It provides
    default IPC de/serialize methods, stores the worker stage and
    maximum batch size, and implements the forward pass pipeline.
    """

    def __init__(self):
        self._stage = "x"  # {"ingress", "x", "egress"}
        self._max_batch_size = 1

    def __str__(self):
        return self.__class__.__name__

    @staticmethod
    def _serialize(data):
        """Defines IPC serialize method"""
        return pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL)

    @staticmethod
    def _deserialize(data):
        """Defines IPC deserialize method"""
        return pickle.loads(data)

    def _set_stage(self, stage):
        self._stage = stage

    def _set_mbs(self, mbs):
        self._max_batch_size = mbs

    @staticmethod
    def unpack(data):
        """Defines service ingress unpack method, overridable"""
        return json.loads(data)

    @staticmethod
    def pack(data):
        """Defines service egress pack method, overridable"""
        return json.dumps()

    def forward(self):
        """Defines worker's computation, must be overridden by all subclasses"""
        raise NotImplementedError
