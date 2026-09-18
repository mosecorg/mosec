# OpenAPI

Starting in v0.9.8, Mosec generates an OpenAPI specification for every registered
route before starting the HTTP server. OpenAPI generation applies to all
{class}`mosec.Worker` subclasses; it does not require
{class}`mosec.mixin.TypedMsgPackMixin`.

For each pipeline, Mosec uses:

- the input annotation of the first worker's `forward` method as the request model;
- the return annotation of the last worker's `forward` method as the response model;
- the boundary workers' `resp_mime_type` values as the request and response content
  types.

For dynamically batched workers, annotate the boundary with `List[Model]`. Mosec
documents one `Model`, because each HTTP request contains one item rather than the
internal batch.

Types supported by [defspec](https://github.com/kemingy/defspec), including standard
Python types and `msgspec.Struct`, produce schemas. If a boundary has no usable type
annotation, its route is still documented but that request or response schema is
omitted.

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
at runtime and changes the wire content type to `application/msgpack`.
