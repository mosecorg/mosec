from typing import Any, List

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
