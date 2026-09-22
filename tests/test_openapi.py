# Copyright 2026 MOSEC Authors
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

import json

import pytest

from mosec.mixin import TypedMsgPackMixin
from mosec.openapi import (
    INFERENCE_ERROR_RESPONSES,
    OPENAPI_METADATA_FILE,
    OPENAPI_SWAGGER_FILE,
    generate_openapi,
    write_openapi_assets,
)
from mosec.worker import SSEWorker, Worker
from tests.services.openapi_service import (
    TypedInference,
    TypedPreprocess,
    UntypedInference,
    UntypedPreprocess,
)


class PlainWorker(Worker):
    def forward(self, data: str) -> int:
        return len(data)


class CustomMimeWorker(Worker):
    req_mime_type = "text/plain"
    resp_mime_type = "application/octet-stream"

    def forward(self, data: str) -> bytes:
        return data.encode()


class AnnotatedSSEWorker(SSEWorker):
    def forward(self, data: str) -> str:
        return data


class UnsupportedModel:
    pass


@pytest.mark.parametrize("typed", [False, True])
@pytest.mark.parametrize("boundary", ["data", "return"])
@pytest.mark.parametrize(
    "annotation",
    [
        pytest.param(UnsupportedModel, id="unsupported-model"),
        pytest.param(dict[str, UnsupportedModel], id="nested-unsupported-model"),
        pytest.param("MissingModel", id="unresolved-name"),
        pytest.param("list[", id="invalid-syntax"),
        pytest.param("list[int, str]", id="malformed-batch"),
    ],
)
def test_generate_openapi_handles_invalid_boundary_types(
    typed, boundary, annotation, mocker, tmp_path
):
    class InvalidWorker(Worker):
        def forward(self, data: int) -> int:
            return data

    InvalidWorker.forward.__annotations__[boundary] = annotation
    warning = mocker.patch("mosec.openapi.logger.warning")

    if typed:

        class InvalidTypedWorker(TypedMsgPackMixin, InvalidWorker):
            pass

        with pytest.raises((TypeError, ValueError, NameError, SyntaxError)):
            write_openapi_assets({"/invalid": [InvalidTypedWorker]}, tmp_path)
        warning.assert_not_called()
        assert not list(tmp_path.iterdir())
        return

    write_openapi_assets(
        {"/invalid": [InvalidWorker], "/valid": [PlainWorker]}, tmp_path
    )
    spec = json.loads((tmp_path / OPENAPI_METADATA_FILE).read_text())
    operation = spec["paths"]["/invalid"]["post"]

    if boundary == "data":
        assert "requestBody" not in operation
        content = operation["responses"]["200"]["content"]
        direction = "request"
    else:
        assert "content" not in operation["responses"]["200"]
        content = operation["requestBody"]["content"]
        direction = "response"
    assert content == {"application/json": {"schema": {"type": "integer"}}}
    assert (
        spec["paths"]["/valid"]
        == generate_openapi({"/valid": [PlainWorker]})["paths"]["/valid"]
    )
    assert (tmp_path / OPENAPI_SWAGGER_FILE).is_file()
    warning.assert_called_once()
    assert warning.call_args.args[:2] == (
        f"Failed to generate {direction} schema for %s: %s",
        "/invalid",
    )


def test_generate_openapi_propagates_unexpected_errors(mocker):
    mocker.patch(
        "mosec.openapi.get_forward_input_type",
        side_effect=RuntimeError("unexpected extraction failure"),
    )

    with pytest.raises(RuntimeError, match="unexpected extraction failure"):
        generate_openapi({"/inference": [PlainWorker]})


@pytest.mark.parametrize("typed_first", [False, True])
def test_generate_openapi_applies_strictness_per_boundary(typed_first, mocker):
    class OrdinaryWorker(Worker):
        def forward(self, data: int) -> int:
            return data

    class TypedWorker(TypedMsgPackMixin):
        def forward(self, data: int) -> int:
            return data

    boundary = "return" if typed_first else "data"
    OrdinaryWorker.forward.__annotations__[boundary] = "list["
    workers = (
        [TypedWorker, OrdinaryWorker] if typed_first else [OrdinaryWorker, TypedWorker]
    )
    warning = mocker.patch("mosec.openapi.logger.warning")
    operation = generate_openapi({"/mixed": workers})["paths"]["/mixed"]["post"]

    if typed_first:
        assert "requestBody" in operation
        assert "content" not in operation["responses"]["200"]
    else:
        assert "requestBody" not in operation
        assert "content" in operation["responses"]["200"]
    warning.assert_called_once()


def test_generate_openapi_for_plain_worker():
    spec = generate_openapi({"/inference": [PlainWorker]})
    operation = spec["paths"]["/inference"]["post"]

    assert operation["requestBody"]["content"] == {
        "application/json": {"schema": {"type": "string"}}
    }
    assert operation["responses"]["200"]["content"] == {
        "application/json": {"schema": {"type": "integer"}}
    }


def test_generate_openapi_uses_separate_request_and_response_mime_types():
    spec = generate_openapi({"/inference": [CustomMimeWorker]})
    operation = spec["paths"]["/inference"]["post"]

    assert set(operation["requestBody"]["content"]) == {"text/plain"}
    assert set(operation["responses"]["200"]["content"]) == {"application/octet-stream"}


def test_generate_openapi_preserves_generic_boundary_types():
    class GenericWorker(Worker):
        def forward(self, data: dict[str, int]) -> dict[str, int]:
            return data

    operation = generate_openapi({"/inference": [GenericWorker]})["paths"][
        "/inference"
    ]["post"]

    assert operation["requestBody"]["content"]["application/json"]["schema"] == {
        "type": "object",
        "additionalProperties": {"type": "integer"},
    }
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "type": "object",
        "additionalProperties": {"type": "integer"},
    }


def test_generate_openapi_omits_invalid_boundary_types():
    class InvalidWorker(Worker):
        # Intentionally malformed to exercise schema generation's fallback.
        def forward(self, data: list[int, str]) -> list[int, str]:  # type: ignore[type-arg]
            return data

    operation = generate_openapi({"/invalid": [InvalidWorker]})["paths"]["/invalid"][
        "post"
    ]

    assert "requestBody" not in operation
    assert "content" not in operation["responses"]["200"]


def test_generate_openapi_sse_request_defaults_to_json():
    spec = generate_openapi({"/stream": [AnnotatedSSEWorker]})
    operation = spec["paths"]["/stream"]["post"]

    assert set(operation["requestBody"]["content"]) == {"application/json"}
    assert set(operation["responses"]["200"]["content"]) == {"text/event-stream"}


def test_generate_openapi_from_worker_boundary_types():
    spec = generate_openapi({"/v1/inference": [TypedPreprocess, TypedInference]})
    operation = spec["paths"]["/v1/inference"]["post"]

    assert operation["requestBody"]["content"] == {
        "application/msgpack": {"schema": {"$ref": "#/$defs/Request"}}
    }
    assert operation["responses"]["200"]["content"] == {
        "application/msgpack": {"schema": {"type": "integer"}}
    }
    assert set(INFERENCE_ERROR_RESPONSES) <= operation["responses"].keys()
    assert "Request" in spec["$defs"]


def test_generate_openapi_omits_only_missing_boundary_types():
    routes = {
        "/no-request": [UntypedPreprocess, TypedInference],
        "/no-response": [TypedPreprocess, UntypedInference],
    }
    spec = generate_openapi(routes)

    no_request = spec["paths"]["/no-request"]["post"]
    assert "requestBody" not in no_request
    assert "content" in no_request["responses"]["200"]

    no_response = spec["paths"]["/no-response"]["post"]
    assert "requestBody" in no_response
    assert "content" not in no_response["responses"]["200"]


def test_write_openapi_assets(tmp_path):
    routes = {"/v1/inference": [TypedPreprocess, TypedInference]}
    write_openapi_assets(routes, tmp_path)

    spec = json.loads((tmp_path / OPENAPI_METADATA_FILE).read_text())
    assert "/v1/inference" in spec["paths"]
    assert {path.name for path in tmp_path.iterdir()} == {
        OPENAPI_METADATA_FILE,
        OPENAPI_SWAGGER_FILE,
    }
    page = (tmp_path / OPENAPI_SWAGGER_FILE).read_text()
    assert "/openapi/metadata.json" in page
    assert "<html" in page.lower()
