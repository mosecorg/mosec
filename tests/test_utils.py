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

from typing import List

from msgspec import Struct

from mosec.mixin.typed_worker import parse_forward_input_type


class Request(Struct):
    name: str


class Demo(Struct):
    def forward(self, _data: Request):
        pass

    def batch_forward(self, _data: List[Request]):
        pass


def test_parse_forward_input_type():
    demo = Demo()

    single = parse_forward_input_type(demo.forward)
    assert single is Request, single

    batch = parse_forward_input_type(demo.batch_forward)
    assert batch is Request, batch
