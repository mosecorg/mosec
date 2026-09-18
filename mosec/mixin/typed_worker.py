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

"""MOSEC type validation mixin."""

# pylint: disable=import-outside-toplevel

from typing import Any, Optional

from mosec.errors import ValidationError
from mosec.utils import get_forward_input_type
from mosec.worker import Worker


class TypedMsgPackMixin(Worker):
    """Enable request type validation with `msgspec` and serde with `msgpack`."""

    # pylint: disable=no-self-use

    req_mime_type = "application/msgpack"
    resp_mime_type = "application/msgpack"
    _input_typ: Optional[Any] = None

    def deserialize(self, data: Any) -> Any:
        """Deserialize and validate request with msgspec."""
        import msgspec

        if self._input_typ is None:
            self._input_typ = get_forward_input_type(self.forward)

        try:
            return msgspec.msgpack.decode(data, type=self._input_typ)
        except msgspec.ValidationError as err:
            raise ValidationError(err) from err

    def serialize(self, data: Any) -> bytes:
        """Serialize with `msgpack`."""
        import msgspec

        return msgspec.msgpack.encode(data)
