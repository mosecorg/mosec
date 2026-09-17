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

"""Generate the static OpenAPI artifacts served by the Rust HTTP process."""

import json
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Dict, List, Mapping, Type

from defspec import OpenAPI, OpenAPIInfo

from mosec.utils import ParseTarget, parse_func_type
from mosec.worker import SSEWorker, Worker

OPENAPI_METADATA_FILE = "openapi-metadata.json"
OPENAPI_SWAGGER_FILE = "openapi-swagger.html"
OPENAPI_METADATA_URL = "/openapi/metadata.json"

INFERENCE_ERROR_RESPONSES = {
    "400": {"description": "BAD_REQUEST"},
    "408": {"description": "REQUEST_TIMEOUT"},
    "413": {"description": "PAYLOAD_TOO_LARGE"},
    "422": {"description": "UNPROCESSABLE_ENTITY"},
    "429": {"description": "TOO_MANY_REQUESTS"},
    "500": {"description": "INTERNAL_SERVER_ERROR"},
    "503": {"description": "SERVICE_UNAVAILABLE"},
}


def _mosec_version() -> str:
    try:
        return version("mosec")
    except PackageNotFoundError:
        return "unknown"


def _forward_type(worker: Type[Worker], target: ParseTarget) -> type | None:
    """Extract the model type and unwrap Mosec's per-batch list annotation."""
    try:
        typ = parse_func_type(worker.forward, target)
    except TypeError:
        return None
    return None if typ is Any else typ


def generate_openapi(routes: Mapping[str, List[Type[Worker]]]) -> Dict[str, Any]:
    """Generate a complete OpenAPI document for all registered routes."""
    openapi = OpenAPI(
        info=OpenAPIInfo(
            title="Mosec API",
            description="OpenAPI generated from Mosec worker type annotations",
            version=_mosec_version(),
        )
    )
    openapi.register_route(
        "/", "get", summary="Liveness health check", response_type=str
    )
    openapi.register_route(
        "/metrics", "get", summary="Prometheus metrics", response_type=str
    )

    for endpoint, workers in routes.items():
        if not workers:
            continue
        request_worker, response_worker = workers[0], workers[-1]
        openapi.register_route(
            endpoint,
            "post",
            summary="Mosec inference",
            request_type=_forward_type(request_worker, ParseTarget.INPUT),
            request_content_type=request_worker.resp_mime_type,
            response_type=_forward_type(response_worker, ParseTarget.RETURN),
            response_content_type=response_worker.resp_mime_type,
        )

    spec = openapi.to_dict()
    for path_item in spec["paths"].values():
        for operation in path_item.values():
            if not operation.get("requestBody"):
                operation.pop("requestBody", None)

    spec["paths"]["/"]["get"]["responses"]["503"] = {
        "description": "SERVICE_UNAVAILABLE"
    }
    for endpoint, workers in routes.items():
        if workers:
            spec["paths"][endpoint]["post"]["responses"].update(
                INFERENCE_ERROR_RESPONSES
            )
            if issubclass(workers[-1], SSEWorker):
                spec["paths"][endpoint]["post"]["responses"]["200"]["description"] = (
                    "Server-sent event stream"
                )
    return spec


def write_openapi_assets(
    routes: Mapping[str, List[Type[Worker]]], output_dir: Path
) -> None:
    """Write the OpenAPI JSON and self-contained viewer pages to ``output_dir``."""
    # offapi eagerly materializes its bundled UI assets. Import it only in the
    # controller process that writes the page, not in every spawned worker.
    from offapi import OpenAPITemplate

    spec = generate_openapi(routes)
    (output_dir / OPENAPI_METADATA_FILE).write_text(
        json.dumps(spec, indent=2), encoding="utf-8"
    )
    (output_dir / OPENAPI_SWAGGER_FILE).write_text(
        OpenAPITemplate.SWAGGER.value.format(spec_url=OPENAPI_METADATA_URL),
        encoding="utf-8",
    )
