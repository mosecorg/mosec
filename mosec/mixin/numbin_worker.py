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

"""MOSEC NumBin IPC worker mixin.

Features:

    * deserialize IPC data with numbin
    * serialize IPC data with numbin

Attention: numbin only supports NumPy ndarray types.
"""

# pylint: disable=import-outside-toplevel

from typing import Any

from mosec.errors import DecodingError, EncodingError


class NumBinIPCMixin:
    """NumBin IPC worker mixin interface."""

    # pylint: disable=no-self-use

    def serialize_ipc(self, data: Any) -> bytes:
        """Serialize with NumBin for the IPC."""
        import numbin

        try:
            data_bytes = numbin.dumps(data)
        except Exception as err:
            raise EncodingError from err
        return data_bytes

    def deserialize_ipc(self, data: bytes) -> Any:
        """Deserialize with NumBin for the IPC."""
        import numbin

        try:
            array = numbin.loads(data)
        except Exception as err:
            raise DecodingError from err
        return array
