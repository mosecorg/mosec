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

import typing

import pytest
from msgspec import Struct

from mosec import Worker
from mosec.utils import get_forward_input_type, get_forward_return_type


class Request(Struct):
    name: str


class Demo(Worker):
    def forward(self, data: Request) -> Request | None:
        pass

    def batch_forward(self, data: list[Request]) -> list[Request]:
        return data

    def generic_forward(self, data: dict[str, int]) -> dict[str, int]:
        return data


def test_parse_forward_input_type():
    demo = Demo()

    single = get_forward_input_type(demo.forward)
    assert single is Request, single

    batch = get_forward_input_type(demo.batch_forward, batched=True)
    assert batch is Request, batch

    assert get_forward_return_type(demo.forward) == Request | None
    assert get_forward_return_type(demo.batch_forward, batched=True) is Request
    assert get_forward_input_type(demo.generic_forward) == dict[str, int]
    assert get_forward_return_type(demo.generic_forward) == dict[str, int]


def test_parse_string_annotations():
    def forward(self, data):
        return data

    forward.__annotations__ = {"data": "Request", "return": "Request | None"}
    assert get_forward_input_type(forward) is Request
    assert get_forward_return_type(forward) == Request | None

    # `from __future__ import annotations` combined with explicit quotes
    # stores the annotation as a doubly-quoted string.
    forward.__annotations__ = {"data": "'Request'", "return": "'Request | None'"}
    assert get_forward_input_type(forward) is Request
    assert get_forward_return_type(forward) == Request | None


def test_invalid_return_annotation_does_not_affect_input():
    def forward(self, data: Request):
        return data

    forward.__annotations__["return"] = "Missing"

    assert get_forward_input_type(forward) is Request
    with pytest.raises(NameError, match="Missing"):
        get_forward_return_type(forward)


def test_batch_annotation_error_mentions_boundary():
    def forward(self, data):
        return data

    # The deprecated bare `typing.List` is the only annotation that reaches
    # the wrong-argument-count batch check, since `list` always takes one.
    forward.__annotations__ = {"data": typing.List, "return": typing.List}

    with pytest.raises(TypeError, match="input annotation"):
        get_forward_input_type(forward, batched=True)
    with pytest.raises(TypeError, match="output annotation"):
        get_forward_return_type(forward, batched=True)
