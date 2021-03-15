import json
import pickle


class ServiceBase:
    """
    This class defines the default service
    decoding/encoding methods.
    """

    def unpack(self):  # ingress
        json.loads()

    def pack(self):  # egress
        json.dumps()


class WorkerBase(ServiceBase):
    """
    This class defines the default inter-worker
    IPC de/serialize methods, worker stage and maximum batch size.
    """

    def __init__(self):
        self._stage = "x"
        self._max_batch_size = 1

    def serialize(self, data):
        return pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL)

    def deserialize(self, data):
        return pickle.loads(data)

    def __call__(self):
        raise NotImplementedError("worker forward pass method not implemented")

    def __repr__(self):
        return self.__class__.__name__
