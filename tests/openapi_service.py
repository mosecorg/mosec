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


import sys
from typing import Any, Dict, List, Type

from msgspec import Struct

from mosec import Server, Worker
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
        print(f"received {data}")
        return data.bin


class UntypedPreprocess(TypedMsgPackMixin, Worker):
    """Dummy preprocess to exit early if the validation failed."""

    def forward(self, data):
        """Input will be parse as the `Request`."""
        print(f"received {data}")
        return data.bin


class TypedInference(TypedMsgPackMixin, Worker):
    """Dummy batch inference."""

    def forward(self, data: List[bytes]) -> List[int]:
        return [len(buf) for buf in data]


class UntypedInference(TypedMsgPackMixin, Worker):
    """Dummy batch inference."""

    def forward(self, data):
        return [len(buf) for buf in data]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Please specify the worker mapping. e.g. TypedPreprocess/TypedInference")
        exit(1)

    worker_mapping: Dict[str, Type[Worker]] = {
        "TypedPreprocess": TypedPreprocess,
        "UntypedPreprocess": UntypedPreprocess,
        "TypedInference": TypedInference,
        "UntypedInference": UntypedInference,
    }

    server = Server(endpoint="/v1/inference")
    preprocess_worker, inference_worker = sys.argv[1].split("/")
    server.append_worker(worker_mapping[preprocess_worker])
    server.append_worker(worker_mapping[inference_worker], max_batch_size=16)
    server.run()
