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

from mosec.openapi import (
    INFERENCE_ERROR_RESPONSES,
    OPENAPI_METADATA_FILE,
    OPENAPI_SWAGGER_FILE,
    generate_openapi,
    write_openapi_assets,
)
from tests.services.openapi_service import (
    TypedInference,
    TypedPreprocess,
    UntypedInference,
    UntypedPreprocess,
)


def test_generate_openapi_from_worker_boundary_types():
    spec = generate_openapi({"/v1/inference": [TypedPreprocess, TypedInference]})
    operation = spec["paths"]["/v1/inference"]["post"]

    assert operation["requestBody"]["content"] == {
        "application/msgpack": {
            "schema": {"$ref": "#/$defs/Request"}
        }
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
