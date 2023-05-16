"""MOSEC plasma worker mixin.

Provide another data transfer way between workers.

The data will be stored in plasma shared memory, while the object ID will be
sent via the original way.

    use case: large image tensors
    benefits: more stable P99 latency

.. warning:: The plasma is deprecated in `pyarrow`. Please use Redis instead.
"""

import warnings
from typing import TYPE_CHECKING, Any

try:
    from pyarrow import plasma  # type: ignore
except ImportError:
    warnings.warn(
        "pyarrow is not installed. PlasmaShmMixin is not available.", ImportWarning
    )

if TYPE_CHECKING:
    from pyarrow import plasma


class PlasmaShmMixin:
    """Plasma shared memory worker mixin interface."""

    # pylint: disable=no-self-use

    plasma_path: str = ""
    _plasma_client = None

    def get_client(self):
        """Get the plasma client. This will create a new one if not exist."""
        if not self.plasma_path:
            raise RuntimeError("plasma path is required")
        if not self._plasma_client:
            self._plasma_client = plasma.connect(self.plasma_path)
        return self._plasma_client

    def serialize_ipc(self, data: Any) -> bytes:
        """Save the data to the plasma server and return the id."""
        client = self.get_client()
        object_id = client.put(data)
        return object_id.binary()

    def deserialize_ipc(self, oid: bytes) -> Any:
        """Get the data from the plasma server and delete it."""
        client = self.get_client()
        object_id = plasma.ObjectID(oid)
        data = client.get(object_id)
        client.delete(object_id)
        return data
