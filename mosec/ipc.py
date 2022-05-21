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

"""Wrapper layer for IPC between workers.

This will be called before sending data or after receiving data through the Protocol.
"""

import abc
from typing import List


class IPCWrapper(abc.ABC):
    """This public class defines the mosec IPC wrapper plugin interface.

    The wrapper has to implement at least `put` and `get` method.
    """

    @abc.abstractmethod
    def put(self, data: List[bytes]) -> List[bytes]:
        """Put bytes to somewhere to get ids, which are sent via protocol.

        Args:
            data (List[bytes]): List of bytes data.

        Returns:
            List[bytes]: List of bytes ID.
        """

    @abc.abstractmethod
    def get(self, ids: List[bytes]) -> List[bytes]:
        """Get bytes from somewhere by ids, which are received via protocol.

        Args:
            ids (List[bytes]): List of bytes ID.

        Returns:
            List[bytes]: List of bytes data.
        """
