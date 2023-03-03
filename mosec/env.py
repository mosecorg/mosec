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
from typing import Dict, List


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
