# Copyright 2023 MOSEC Authors
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

"""Provide useful utils to inspect function type."""

import inspect
from enum import Enum
from typing import List


class ParseTarget(Enum):
    """Enum to specify the target of parsing func type."""

    INPUT = "INPUT"
    RETURN = "RETURN"


def parse_func_type(func, target: ParseTarget) -> type:
    """Parse the input type of the target function.

    - single request: return the type
    - batch request: return the list item type
    """
    sig = inspect.signature(func)
    index = 0 if inspect.ismethod(func) else 1
    name = func.__name__
    if target == ParseTarget.INPUT:
        params = list(sig.parameters.values())
        if len(params) < index + 1:
            raise TypeError(
                f"`{name}` method doesn't have enough({index + 1}) parameters"
            )
        typ = params[index].annotation
    else:
        typ = sig.return_annotation

    origin = getattr(typ, "__origin__", None)
    if origin is None:
        return typ
    # GenericAlias, `func` could be batch inference
    if origin is list or origin is List:
        if not hasattr(typ, "__args__") or len(typ.__args__) != 1:  # type: ignore
            raise TypeError(
                f"`{name}` with dynamic batch should use "
                "`List[Struct]` as the input annotation"
            )
        return typ.__args__[0]  # type: ignore
    raise TypeError(f"unsupported type {typ}")
