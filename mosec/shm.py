import pickle
from typing import Any, Callable, List

try:
    from pyarrow import plasma  # type: ignore
except ImportError:
    """
    We don't include pyarrow as our dependency.
    Users should install it as third party to enable
    the shared memory IPC feature.
    """


class ShmClient:
    def __init__(self, shm_path: str = "") -> None:
        """Initialize a client which may utilize plasma as shared memory.

        Args:
            shm_path (str, optional): path of the plasma server. Defaults to "".
        """
        self.client = plasma.connect(shm_path)

    def put(self, data: Any) -> plasma.ObjectID:
        """Individual put"""
        return self.client.put(data)

    def get(self, object_ids: List[plasma.ObjectID]) -> List[Any]:
        """Batch get"""
        objects = self.client.get(object_ids)
        self.client.delete(object_ids)
        return objects


class ShmWrapper:
    def __init__(
        self,
        shm_cli: ShmClient,
        serializer: Callable = pickle.dumps,
        deserializer: Callable = pickle.loads,
    ) -> None:
        """Wrap the shm plugin for protocol.

        Args:
            serializer (Callable, optional): serializer before put.
                Defaults to pickle.dumps.
            deserializer (Callable, optional): deserializer after get.
                Defaults to pickle.loads.
        """
        self.shm_cli = shm_cli
        self.serializer = serializer
        self.deserializer = deserializer

    def wrap_decoder(self, decoder: Callable) -> Callable:
        def wrapped(batch_bytes: List[bytes]) -> List[Any]:
            batch_ids = [decoder(x) for x in batch_bytes]
            batch_data = self.shm_cli.get(batch_ids)
            return [self.deserializer(x) for x in batch_data]

        return wrapped

    def wrap_encoder(self, encoder: Callable) -> Callable:
        def wrapped(data: Any) -> bytes:
            data_bytes = encoder(data)
            object_id = self.shm_cli.put(data_bytes)
            return self.serializer(object_id)

        return wrapped
