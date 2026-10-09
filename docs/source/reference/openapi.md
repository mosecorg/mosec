# OpenAPI

Starting in v0.9.8, Mosec generates an OpenAPI specification for every registered
route before starting the HTTP server. The document uses OpenAPI 3.2.0, with
shared models under `components.schemas`. OpenAPI generation applies to all
{class}`mosec.Worker` subclasses; it does not require
{class}`mosec.mixin.TypedMsgPackMixin`.

For each pipeline, Mosec uses:

- the input annotation of the first worker's `forward` method as the request model;
- the return annotation of the last worker's `forward` method as the response model;
- the first worker's `req_mime_type` as the request content type;
- the last worker's `resp_mime_type` as the response content type.

For dynamically batched workers, annotate the boundary with `List[Model]`. Mosec
documents one `Model`, because each HTTP request contains one item rather than the
internal batch. This applies when the boundary runtime has `max_batch_size > 1`.
With `max_batch_size=1`, `List[Model]` describes an array in the HTTP body. Request
and response batching are determined independently from the first and last
runtimes, so the same worker class can be used with different batch settings.

Types supported by [defspec](https://github.com/kemingy/defspec), including standard
Python types and `msgspec.Struct`, produce schemas. If a boundary has no usable type
annotation, its route is still documented but that request or response schema is
omitted. For ordinary workers, malformed annotations, unresolved type names,
unsupported model types, and conflicting shared model names produce a warning
and omit only the affected schema. Shared model names must identify the same
schema across all routes; rename distinct models that share a name.
Typed schemas take priority over ordinary schemas regardless of route order.
For `TypedMsgPackMixin` workers, invalid annotations and collisions between typed
schemas fail startup. Missing annotations and `Any` still omit the schema.
Unexpected errors propagate for all workers.
Schema validation also runs with `--dry-run`, before any runtime configuration or
OpenAPI files are written.
Normal startup writes both OpenAPI assets before starting the Rust HTTP process
or Python workers. If writing assets or starting Rust fails, Mosec cleans up the
runtime directory and propagates the error.

## Migration from v0.9.7

- OpenAPI documents now use version 3.2.0. Update client generators and validators
  that only support 3.1. Shared models remain under `components.schemas`.
- `Worker.get_forward_json_schema`, `MOSEC_REF_TEMPLATE`, and
  `mosec.utils.ParseTarget`/`parse_func_type` have been removed. Replace custom
  schema overrides with supported `forward` type annotations.
- Invalid boundary annotations on `TypedMsgPackMixin` workers now fail validation
  at startup and with `--dry-run`. Fix unresolved names, malformed annotations,
  and unsupported model types before running the service.
- For typed workers with `max_batch_size=1`, a `List[T]` input now validates an
  array of `T`. With dynamic batching enabled, it still validates one `T` per
  request. Set `max_batch_size` to match the way `forward` handles its input.
- Set `req_mime_type` explicitly for custom deserializers. Setting
  `resp_mime_type` now controls only the response documentation.

## Example

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
