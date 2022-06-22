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

import logging

from .server import Server
from .worker import Worker

try:
    from ._version import __version__  # type: ignore
except ImportError:
    from setuptools_scm import get_version  # type: ignore

    __version__ = get_version(root="..", relative_to=__file__)

__all__ = ["Server", "Worker"]

# setup library logging
logging.getLogger(__name__).addHandler(logging.NullHandler())
