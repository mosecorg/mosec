# Copyright 2023 MOSEC Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""MOSEC plasma worker mixin.

Provide another data transfer way between workers.

The data will be stored in plasma shared memory, while the object ID will be
sent via the original way.

    use case: large image tensors
    benefits: more stable P99 latency

```{warning}
The plasma is deprecated in `pyarrow`. Please use Redis instead.
```
"""

import warnings
from os import environ
from typing import Any

from mosec.worker import Worker

try:
    from pyarrow import plasma  # type: ignore
except ImportError:
    warnings.warn(
        "pyarrow is not installed. PlasmaShmMixin is not available.", ImportWarning
    )


_PLASMA_PATH_ENV = "MOSEC_INTERNAL_PLASMA_PATH"


class PlasmaShmIPCMixin(Worker):
    """Plasma shared memory worker mixin interface."""

    # pylint: disable=no-self-use

    _plasma_client = None

    @classmethod
    def set_plasma_path(cls, path: str):
        """Set the plasma service path."""
        environ[_PLASMA_PATH_ENV] = path

    def _get_client(self):
        """Get the plasma client. This will create a new one if not exist."""
        if not self._plasma_client:
            path = environ.get(_PLASMA_PATH_ENV)
            if not path:
                raise RuntimeError(
                    "please set the plasma path with "
                    "`PlasmaShmIPCMixin.set_plasma_path()`"
                )
            self._plasma_client = plasma.connect(path)
        return self._plasma_client

    def serialize_ipc(self, data: Any) -> bytes:
        """Save the data to the plasma server and return the id."""
        client = self._get_client()
        object_id = client.put(super().serialize_ipc(data))
        return object_id.binary()

    def deserialize_ipc(self, data: bytes) -> Any:
        """Get the data from the plasma server and delete it."""
        client = self._get_client()
        object_id = plasma.ObjectID(bytes(data))
        obj = super().deserialize_ipc(client.get(object_id))
        client.delete((object_id,))
        return obj
