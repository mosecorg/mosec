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
import sys
from enum import Enum
from typing import Any, List


def get_annotations(func) -> dict:
    """Get the annotations of a class method.

    This will evaluation the annotations of the method and return a dict.
    The implementation is based on the `inspect.get_annotations` (Py>=3.10).

    ``eval_str=True`` since ``from __future__ import annotations`` will change
    all the annotations to string.
    """
    if sys.version_info >= (3, 10):
        return inspect.get_annotations(func, eval_str=True)
    annotations = getattr(func, "__annotations__", None)
    obj_globals = getattr(func, "__globals__", None)
    if annotations is None:
        return {}
    if not isinstance(annotations, dict):
        raise TypeError(f"{func.__name__} annotations must be a dict or None")
    return {
        key: value if not isinstance(value, str) else eval(value, obj_globals)
        for key, value in annotations.items()
    }


class ParseTarget(Enum):
    """Enum to specify the target of parsing func type."""

    INPUT = "INPUT"
    RETURN = "RETURN"


def parse_func_type(func, target: ParseTarget) -> type:
    """Parse the input type of the target function.

    - single request: return the type
    - batch request: return the list item type
    """
    annotations = get_annotations(func)
    name = func.__name__
    typ = Any
    if target == ParseTarget.INPUT:
        for key in annotations:
            if key != "return":
                typ = annotations[key]
                break
    else:
        typ = annotations.get("return", Any)

    origin = getattr(typ, "__origin__", None)
    if origin is None:
        return typ  # type: ignore
    # GenericAlias, `func` could be batch inference
    if origin is list or origin is List:
        if not hasattr(typ, "__args__") or len(typ.__args__) != 1:  # type: ignore
            raise TypeError(
                f"`{name}` with dynamic batch should use "
                "`List[Struct]` as the input annotation"
            )
        return typ.__args__[0]  # type: ignore
    raise TypeError(f"unsupported type {typ}")
