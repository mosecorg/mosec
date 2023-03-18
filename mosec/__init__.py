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

"""MOSEC is a machine learning model serving framework."""

from mosec.errors import (
    ClientError,
    DecodingError,
    EncodingError,
    ServerError,
    ValidationError,
)
from mosec.log import get_logger
from mosec.server import Server
from mosec.worker import Worker

try:
    from mosec._version import __version__  # type: ignore
except ImportError:
    from setuptools_scm import get_version  # type: ignore

    __version__ = get_version(root="..", relative_to=__file__)

__all__ = [
    "Server",
    "Worker",
    "ServerError",
    "ClientError",
    "ValidationError",
    "EncodingError",
    "DecodingError",
    "get_logger",
]
