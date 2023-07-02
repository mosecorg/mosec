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

"""Test MsgPack mixin."""

from typing import Any, List

from msgspec import Struct

from mosec import Server, Worker
from mosec.mixin import TypedMsgPackMixin


class Request(Struct):
    media: str
    binary: bytes


class Inference(TypedMsgPackMixin, Worker):
    def forward(self, data: List[Request]) -> Any:
        return [len(req.binary) for req in data]


if __name__ == "__main__":
    server = Server()
    server.append_worker(Inference, max_batch_size=4)
    server.run()
