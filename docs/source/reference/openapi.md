# OpenAPI

Starting in v0.9.8, Mosec generates an OpenAPI specification for every registered
route before starting the HTTP server. OpenAPI generation applies to all
{class}`mosec.Worker` subclasses; it does not require
{class}`mosec.mixin.TypedMsgPackMixin`.

For each pipeline, Mosec uses:

- the input annotation of the first worker's `forward` method as the request model;
- the return annotation of the last worker's `forward` method as the response model;
- the first worker's `req_mime_type` as the request content type;
- the last worker's `resp_mime_type` as the response content type.

For dynamically batched workers, annotate the boundary with `List[Model]`. Mosec
documents one `Model`, because each HTTP request contains one item rather than the
internal batch.

Types supported by [defspec](https://github.com/kemingy/defspec), including standard
Python types and `msgspec.Struct`, produce schemas. If a boundary has no usable type
annotation, its route is still documented but that request or response schema is
omitted. Invalid annotations and unsupported model types produce a warning and
omit only the affected schema; they do not prevent startup. This fallback applies
to OpenAPI generation, not runtime request validation or serialization.

```python
from dataclasses import dataclass

from mosec import Worker


@dataclass
class Request:
    text: str


class Inference(Worker):
    def forward(self, data: Request) -> int:
        return len(data.text)
```

The generated endpoints are:

- `/openapi/metadata.json` for the OpenAPI document;
- `/openapi/swagger/` for the self-contained Swagger UI.

`TypedMsgPackMixin` serves a separate purpose: it uses `msgspec` to validate requests
at runtime and changes both wire content types to `application/msgpack`.

On `Worker`, both MIME attributes default to `application/json`. A worker that
customizes request deserialization can set `req_mime_type` without changing its
response content type. For example, `SSEWorker` keeps the JSON request default and
sets only `resp_mime_type` to `text/event-stream`.
