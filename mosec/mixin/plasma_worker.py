"""MOSEC plasma worker mixin.

Provide another data transfer way between workers.

The data will be stored in plasma shared memory, while the object ID will be
sent via the original way.

    use case: large image tensors
    benefits: more stable P99 latency

.. warning:: The plasma is deprecated in `pyarrow`. Please use Redis instead.
"""

import warnings
from os import environ
from typing import TYPE_CHECKING, Any

from mosec.worker import Worker

try:
    from pyarrow import plasma  # type: ignore
except ImportError:
    warnings.warn(
        "pyarrow is not installed. PlasmaShmMixin is not available.", ImportWarning
    )

if TYPE_CHECKING:
    from pyarrow import plasma


_PLASMA_PATH_ENV = "MOSEC_INTERNAL_PLASMA_PATH"


class PlasmaShmMixin(Worker):
    """Plasma shared memory worker mixin interface."""

    # pylint: disable=no-self-use

    _plasma_client = None

    @classmethod
    def set_plasma_path(cls, path: str):
        """Set the plasma service path."""
        environ[_PLASMA_PATH_ENV] = path

    def get_client(self):
        """Get the plasma client. This will create a new one if not exist."""
        if not self._plasma_client:
            path = environ.get(_PLASMA_PATH_ENV)
            if not path:
                raise RuntimeError("")
            self._plasma_client = plasma.connect(path)
        return self._plasma_client

    def serialize_ipc(self, data: Any) -> bytes:
        """Save the data to the plasma server and return the id."""
        client = self.get_client()
        object_id = client.put(data)
        return super().serialize_ipc(object_id.binary())

    def deserialize_ipc(self, data: bytes) -> Any:
        """Get the data from the plasma server and delete it."""
        client = self.get_client()
        object_id = plasma.ObjectID(super().deserialize_ipc(data))
        obj = client.get(object_id)
        client.delete((object_id,))
        return obj
