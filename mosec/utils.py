# Copyright 2025 MOSEC Authors
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
import os
import sysconfig
from pathlib import Path
from typing import Any, Optional, get_args, get_origin


# adopted from https://github.com/PyO3/maturin/blob/main/maturin/__main__.py
# License: Apache-2.0 or MIT
def get_mosec_path() -> Optional[Path]:
    """Get `mosec` binary path."""
    SCRIPT_NAME = "mosec"

    def script_dir(scheme: str) -> str:
        return sysconfig.get_path("scripts", scheme)

    def script_exists(dir: str) -> bool:
        for _, _, files in os.walk(dir):
            for f in files:
                name, *_ = os.path.splitext(f)
                if name == SCRIPT_NAME:
                    return True

        return False

    paths = list(
        filter(
            script_exists,
            filter(os.path.exists, map(script_dir, sysconfig.get_scheme_names())),
        )
    )

    if paths:
        return Path(paths[0]) / SCRIPT_NAME

    return None


def _unwrap_batch_type(func, typ: Any) -> Any:
    """Return one request item from Mosec's ``list[T]`` batch annotation."""
    if get_origin(typ) is not list:
        return typ

    args = get_args(typ)
    if len(args) != 1:
        raise TypeError(
            f"`{func.__name__}` with dynamic batch should use "
            "`List[Struct]` as the input annotation"
        )
    return args[0]


def get_forward_input_type(func) -> Any:
    """Return the type of one request passed to ``forward``.

    Mosec passes each HTTP request as one item in a dynamic batch, so a
    ``list[T]`` parameter annotation represents an individual ``T``.
    """
    annotations = inspect.get_annotations(func, eval_str=True)
    typ = next((value for name, value in annotations.items() if name != "return"), Any)
    return _unwrap_batch_type(func, typ)


def get_forward_return_type(func) -> Any:
    """Return the type of one response returned from ``forward``.

    A ``list[T]`` return annotation represents the per-request ``T`` values
    produced by a dynamically batched worker.
    """
    typ = inspect.get_annotations(func, eval_str=True).get("return", Any)
    return _unwrap_batch_type(func, typ)
