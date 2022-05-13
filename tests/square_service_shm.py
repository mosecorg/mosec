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

from functools import partial
from typing import List

from pyarrow import plasma  # type: ignore

from mosec import Server, Worker
from mosec.errors import ValidationError
from mosec.plugins import PlasmaShmWrapper


class SquareService(Worker):
    def forward(self, data: List[dict]) -> List[dict]:
        try:
            result = [{"x": int(req["x"]) ** 2} for req in data]
        except KeyError as err:
            raise ValidationError(err)
        return result


class DummyPostprocess(Worker):
    """This dummy stage is added to test the shm IPC"""

    def forward(self, data: dict) -> dict:
        assert isinstance(data.get("x"), int), f"wrong data type: {data}"
        return data


if __name__ == "__main__":
    # initialize a 20Mb object store as shared memory
    with plasma.start_plasma_store(plasma_store_memory=20 * 1000 * 1000) as (
        shm_path,
        shm_process,
    ):
        server = Server(
            ipc_wrapper=partial(  # defer the wrapper init to worker processes
                PlasmaShmWrapper,
                shm_path=shm_path,
            )
        )
        server.register_daemon("plasma_server", shm_process)
        server.append_worker(SquareService, max_batch_size=8)
        server.append_worker(DummyPostprocess, num=2)
        server.run()
