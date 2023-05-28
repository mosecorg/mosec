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
import warnings
from typing import Any, List

from mosec.errors import ValidationError
from mosec.worker import Worker

try:
    import msgspec  # type: ignore
except ImportError:
    warnings.warn("msgpack is required for TypedMsgPackMixin", ImportWarning)


def parse_forward_input_type(func, target="parameters", index=0):
    """Parse the input type of the forward function.

    - single request: return the type
    - batch request: return the list item type
    """
    sig = inspect.signature(func)
    if target == "parameters":
        params = list(sig.parameters.values())
        if len(params) < 1:
            raise TypeError("`forward` method doesn't have enough(1) parameters")
        typ = params[index].annotation
    else:
        typ = sig.return_annotation
        if typ is inspect.Signature.empty:
            raise TypeError("`forward` method doesn't have return annotation")
        if not inspect.isclass(typ):
            typ = msgspec.inspect.type_info(typ).__class__

    origin = getattr(typ, "__origin__", None)
    if origin is None:
        return typ
    # GenericAlias, `func` could be batch inference
    if origin is list or origin is List:
        if not hasattr(typ, "__args__") or len(typ.__args__) != 1:  # type: ignore
            raise TypeError(
                "`forward` with dynamic batch should use "
                "`List[Struct]` as the input annotation"
            )
        return typ.__args__[0]  # type: ignore
    raise TypeError(f"unsupported type {typ}")


def parse_instance_param_typ(func):
    """Parse the input type of the forward function for instance."""
    return parse_forward_input_type(func, "parameters", 0)


def parse_cls_param_typ(func):
    """Parse the input type of the forward function for class."""
    return parse_forward_input_type(func, "parameters", 1)


def parse_cls_return_typ(func):
    """Parse the return type of the forward function for class."""
    return parse_forward_input_type(func, "return")


class TypedMsgPackMixin(Worker):
    """Enable request type validation with `msgspec` and serde with `msgpack`."""

    # pylint: disable=no-self-use

    resp_mime_type = "application/msgpack"
    _input_type = None

    def _get_input_type(self):
        """Get the input type from annotations."""
        if self._input_type is None:
            self._input_type = parse_instance_param_typ(self.forward)
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
