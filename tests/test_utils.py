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

"""Test util functions."""

from typing import List, Optional

from msgspec import Struct

from mosec import Worker
from mosec.utils import get_forward_input_type, get_forward_return_type


class Request(Struct):
    name: str


class Demo(Worker):
    def forward(self, data: Request) -> Optional[Request]:
        pass

    def batch_forward(self, data: List[Request]) -> List[Request]:
        return data

    def generic_forward(self, data: dict[str, int]) -> dict[str, int]:
        return data


def test_parse_forward_input_type():
    demo = Demo()

    single = get_forward_input_type(demo.forward)
    assert single is Request, single

    batch = get_forward_input_type(demo.batch_forward)
    assert batch is Request, batch

    assert get_forward_return_type(demo.forward) == Optional[Request]
    assert get_forward_return_type(demo.batch_forward) is Request
    assert get_forward_input_type(demo.generic_forward) == dict[str, int]
    assert get_forward_return_type(demo.generic_forward) == dict[str, int]
