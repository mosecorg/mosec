import abc
from typing import List


class IPCWrapper(abc.ABC):
    """
    This public class defines the mosec IPC wrapper plugin interface.
    The wrapper has to at least implement `put` and `get` method.
    """

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
