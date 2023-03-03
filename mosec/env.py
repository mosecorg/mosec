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

"""Environment variables related functions."""

from __future__ import annotations

import contextlib
import os
import warnings
from argparse import Namespace
from typing import Dict, List

MOSEC_ENV_PREFIX = "MOSEC_"
MOSEC_ENV_CONFIG = {
    "path": str,
    "capacity": int,
    "timeout": int,
    "address": str,
    "port": int,
    "namespace": str,
    "debug": bool,
    "dry_run": bool,
}


@contextlib.contextmanager
def env_var_context(env: None | List[Dict[str, str]], index: int):
    """Manage the environment variables for a worker process."""
    default: Dict = {}
    try:
        if env is not None:
            for key, value in env[index].items():
                default[key] = os.getenv(key, "")
                os.environ[key] = value
        yield None
    finally:
        for key, value in default.items():
            os.environ[key] = value


def get_env_namespace(prefix: str = MOSEC_ENV_PREFIX) -> Namespace:
    """Read the config from environment variables before the argument parsing.

    Priority: CLI > env > default value.
    """
    namespace = Namespace()
    for name, converter in MOSEC_ENV_CONFIG.items():
        var = f"{prefix}{name.upper()}"
        value = os.environ.get(var)
        if not value:
            continue
        try:
            val = converter(value)
        except ValueError as err:
            warnings.warn(
                f"failed to convert env {var}={value} to type {converter} {err}, "
                "will skip this one",
            )
        else:
            setattr(namespace, name, val)

    return namespace
