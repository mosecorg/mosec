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

from typing import Any, Dict, Optional, Tuple

from mosec import get_logger
from mosec.errors import ValidationError
from mosec.utils import ParseTarget, parse_func_type
from mosec.worker import Worker

logger = get_logger()


class TypedMsgPackMixin(Worker):
    """Enable request type validation with `msgspec` and serde with `msgpack`."""

    # pylint: disable=no-self-use

    resp_mime_type = "application/msgpack"
    _input_typ: Optional[type] = None

    def deserialize(self, data: Any) -> Any:
        """Deserialize and validate request with msgspec."""
        import msgspec

        if self._input_typ is None:
            self._input_typ = parse_func_type(self.forward, ParseTarget.INPUT)

        try:
            return msgspec.msgpack.decode(data, type=self._input_typ)
        except msgspec.ValidationError as err:
            raise ValidationError(err) from err

    def serialize(self, data: Any) -> bytes:
        """Serialize with `msgpack`."""
        import msgspec

        return msgspec.msgpack.encode(data)

    @classmethod
    def get_forward_json_schema(
        cls, target: ParseTarget, ref_template: str
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Get the JSON schema of the forward function."""
        import msgspec

        schema: Dict[str, Any]
        comp_schema: Dict[str, Any]
        schema, comp_schema = {}, {}
        typ = parse_func_type(cls.forward, target)
        try:
            (schema,), comp_schema = msgspec.json.schema_components(
                [typ], ref_template=ref_template
            )
        except TypeError as err:
            logger.warning(
                "Failed to generate JSON schema for %s: %s", cls.__name__, err
            )
        return schema, comp_schema
