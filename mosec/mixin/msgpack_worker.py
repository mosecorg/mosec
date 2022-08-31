# Copyright 2022 MOSEC Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""MOSEC msgpack worker mixin.

Features:

    * deserialize request body with msgpack
    * serialize response body with msgpack
"""


import warnings
from typing import Any

from ..errors import DecodingError, EncodingError

try:
    import msgpack  # type: ignore
except ImportError:
    warnings.warn("msgpack is required for MsgpackWorker", ImportWarning)


class MsgpackMixin:
    """Msgpack worker mixin interface."""

    # pylint: disable=no-self-use

    def serialize(self, data: Any) -> bytes:
        """Serialize with msgpack for the last stage (egress).

        Arguments:
            data: the [_*same type_][mosec.worker.Worker--note]

        Returns:
            the bytes you want to put into the response body

        Raises:
            EncodingError: if the data cannot be serialized with msgpack
        """
        try:
            data_bytes = msgpack.packb(data)
        except Exception as err:
            raise EncodingError from err
        return data_bytes

    def deserialize(self, data: bytes) -> Any:
        """Deserialize method for the first stage (ingress).

        Arguments:
            data: the raw bytes extracted from the request body

        Returns:
            [_*same type_][mosec.worker.Worker--note]

        Raises:
            DecodingError: if the data cannot be deserialized with msgpack
        """
        try:
            data_msg = msgpack.unpackb(data, use_list=False)
        except Exception as err:
            raise DecodingError from err
        return data_msg
