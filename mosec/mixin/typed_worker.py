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

import inspect
from typing import Any

import msgspec

from mosec.errors import ValidationError
from mosec.worker import Worker


class TypedMsgPackMixin(Worker):
    """Enable request type validation with `msgspec` and serde with `msgpack`."""

    # pylint: disable=no-self-use

    _input_type = None

    def _get_input_type(self):
        """Get the input type from annotations."""
        if self._input_type is None:
            sig = inspect.signature(self.forward)
            params = list(sig.parameters.values())
            if len(params) < 1:
                raise RuntimeError("`forward` method doesn't have enough(1) parameters")
            self._input_type = params[0].annotation
        return self._input_type

    def deserialize(self, data: Any) -> bytes:
        """Deserialize and validate request with msgspec."""
        schema = self._get_input_type()
        if not issubclass(schema, msgspec.Struct):
            # skip other annotation type
            return super().deserialize(data)

        try:
            return msgspec.msgpack.decode(data, type=schema)
        except msgspec.ValidationError as err:
            raise ValidationError(err)  # pylint: disable=raise-missing-from

    def serialize(self, data: Any) -> bytes:
        """Serialize with `msgpack`."""
        return msgspec.msgpack.encode(data)
