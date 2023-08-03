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

"""Test multi-route service."""

from typing import Any

from msgspec import Struct

from mosec import Runtime, Server, Worker
from mosec.mixin import TypedMsgPackMixin


class Request(Struct):
    """User request struct."""

    # pylint: disable=too-few-public-methods

    bin: bytes
    name: str = "test"


class TypedPreprocess(TypedMsgPackMixin, Worker):
    """Dummy preprocess to exit early if the validation failed."""

    def forward(self, data: Request) -> Any:
        """Input will be parse as the `Request`."""
        print(f"received from {data.name} with {data.bin!r}")
        return data.bin


class Preprocess(Worker):
    """Dummy preprocess worker."""

    def deserialize(self, data: bytes) -> Any:
        return data

    def forward(self, data: Any) -> Any:
        return data


class Inference(Worker):
    """Dummy inference worker."""

    def forward(self, data: Any) -> Any:
        return [{"length": len(datum)} for datum in data]


class TypedPostprocess(TypedMsgPackMixin, Worker):
    """Dummy postprocess with msgpack."""

    def forward(self, data: Any) -> Any:
        return data


if __name__ == "__main__":
    server = Server()
    typed_pre = Runtime(TypedPreprocess)
    pre = Runtime(Preprocess)
    inf = Runtime(Inference, max_batch_size=16)
    typed_post = Runtime(TypedPostprocess)
    server.register_runtime(
        {
            "/v1/inference": [typed_pre, inf, typed_post],
            "/inference": [pre, inf],
        }
    )
    server.run()
