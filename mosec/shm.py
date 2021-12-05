import logging
from typing import Any, List

try:
    from pyarrow import plasma  # type: ignore
except ImportError:
    """
    We don't include pyarrow as our dependency.
    Users should install it as third party to enable
    the shared memory IPC feature.
    """
    pass

logger = logging.getLogger(__name__)


class ShmClient:
    def __init__(self, shm_path: str = "", name: str = "") -> None:
        """Initialize a client which may utilize plasma as shared memory.

        Args:
            shm_path (str, optional): path of the plasma server. Defaults to "".
            name (str, optional): name of this client. Defaults to "".
        """
        self.client = None
        self.name = name
        if shm_path:
            self.client = plasma.connect(shm_path)
            logger.info(f"{self.name} shm connected to {shm_path}")

    def put(self, data: Any) -> Any:
        """Individual put."""
        if self.client is None:
            return data
        return self.client.put(data)

    def get(self, maybe_ids: List[Any]) -> List[Any]:
        """Batch get."""
        if self.client is None:
            return maybe_ids
        objects = self.client.get(maybe_ids)
        self.client.delete(maybe_ids)
        return objects
