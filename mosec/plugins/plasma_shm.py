# Copyright 2022 MOSEC
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

from typing import List

try:
    from pyarrow import plasma  # type: ignore
except ImportError:
    """
    We do not enforce the installation of third party libaries for
    plugins, because users may not enable them.
    """

from ..ipc import IPCWrapper


class PlasmaShmWrapper(IPCWrapper):
    """
    This public class is an example implementation of the `IPCWrapper`.
    It utilizes `pyarrow.plasma` as the in-memory object store for
    potentially more efficient data transfer.
    """

    def __init__(self, shm_path: str) -> None:
        """Initialize the IPC Wrapper as a plasma client.

        Args:
            shm_path (str): path of the plasma server.
        """
        self.client = plasma.connect(shm_path)

    def _put_plasma(self, data: List[bytes]) -> List[plasma.ObjectID]:
        """Batch put into plasma memory store"""
        return [self.client.put(x) for x in data]

    def _get_plasma(self, object_ids: List[plasma.ObjectID]) -> List[bytes]:
        """Batch get from plasma memory store"""
        objects = self.client.get(object_ids)
        self.client.delete(object_ids)
        return objects

    def put(self, data: List[bytes]) -> List[bytes]:
        object_ids = self._put_plasma(data)
        return [id.binary() for id in object_ids]

    def get(self, ids: List[bytes]) -> List[bytes]:
        object_ids = [plasma.ObjectID(id) for id in ids]
        return self._get_plasma(object_ids)
