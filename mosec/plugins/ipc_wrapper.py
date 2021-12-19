import abc
import pickle
from typing import List

try:
    from pyarrow import plasma  # type: ignore
except ImportError:
    """
    We do not enforce the installation of third party libaries for
    plugins, because users may not enable them.
    """


class IPCWrapper(abc.ABC):
    @abc.abstractmethod
    def put(self, data: List[bytes]) -> List[bytes]:
        """Put bytes to somewhere to get ids, which are sent via protocol.

        Args:
            data (List[bytes]): List of bytes data.

        Returns:
            List[bytes]: List of bytes ID.
        """

    @abc.abstractmethod
    def get(self, ids: List[bytes]) -> List[bytes]:
        """Get bytes from somewhere by ids, which are received via protocol.

        Args:
            ids (List[bytes]): List of bytes ID.

        Returns:
            List[bytes]: List of bytes data.
        """


class PlasmaShmWrapper(IPCWrapper):
    def __init__(self, shm_path: str) -> None:
        """Initialize the IPC Wrapper as a plasma client.

        Args:
            shm_path (str): path of the plasma server.
        """
        self.client = plasma.connect(shm_path)

    def put_plasma(self, data: List[bytes]) -> List[plasma.ObjectID]:
        """Batch put into plasma memory store"""
        return [self.client.put(x) for x in data]

    def get_plasma(self, object_ids: List[plasma.ObjectID]) -> List[bytes]:
        """Batch get from plasma memory store"""
        objects = self.client.get(object_ids)
        self.client.delete(object_ids)
        return objects

    def put(self, data: List[bytes]) -> List[bytes]:
        object_ids = self.put_plasma(data)
        return [pickle.dumps(id) for id in object_ids]

    def get(self, ids: List[bytes]) -> List[bytes]:
        object_ids = [pickle.loads(id) for id in ids]
        return self.get_plasma(object_ids)
