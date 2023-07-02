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

"""Test basic `forward` logic for single/concurrency request."""

from typing import List

from mosec import Server, Worker
from mosec.errors import ValidationError


class SquareService(Worker):
    def forward(self, data: List[dict]) -> List[dict]:
        try:
            result = [{"x": int(req["x"]) ** 2} for req in data]
        except KeyError as err:
            raise ValidationError(err) from err
        return result


if __name__ == "__main__":
    server = Server(endpoint="/v1/inference")
    server.append_worker(SquareService, max_batch_size=8)
    server.run()
