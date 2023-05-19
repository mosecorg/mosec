# Validate Request

This example shows how to use the `TypedMsgPackMixin` to validate the request with the help of [`msgspec`](https://github.com/jcrist/msgspec).

Request validation can provide the following benefits:

- The client can know the exact expected data schema from the type definition.
- Validation failure will return the details of the failure reason to help the client debug.
- Ensure that the service is working on the correct data without fear.

First of all, define the request type with `msgspec.Struct` like:

```python
class Request(msgspec.Struct):
    media: str
    binary: bytes
```

Then, apply the `TypedMsgPackMixin` mixin and add the type you defined to the annotation of `forward(self, data)`:

```python
class Inference(TypedMsgPackMixin, Worker):
    def forward(self, data: Request):
        pass
```

```{note}
If you are using dynamic **batch** inference as the first stage, just use the `List[Request]` as the annotation.
```

You can check the full demo code below.

## Server

```{include} ../../../examples/type_validation/server.py
:code: python
```

## Client

```{include} ../../../examples/type_validation/client.py
:code: python
```

## Test

```shell
python client.py
```
