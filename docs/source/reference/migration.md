# Migration Guide

This guide will help you migrate from other frameworks to `mosec`.

## From the `Triton Inference Server`

Both [`PyTriton`](https://github.com/triton-inference-server/pytriton) and [`Triton Python Backend`](https://github.com/triton-inference-server/python_backend) are using [`Triton Inference Server`](https://github.com/triton-inference-server).

- `mosec` doesn't require a specific client, you can use any HTTP client library
- dynamic batching is configured when calling the [`append_worker`](mosec.server.Server.append_worker)
- `mosec` doesn't need to declare the `inputs` and `outputs`. If you want to validate the request, you can use the [`TypedMsgPackMixin`](mosec.mixin.typed_worker.TypedMsgPackMixin) (ref [Validate Request](https://mosecorg.github.io/mosec/examples/validate.html))

### `Triton Python Backend`

- change the `TritonPythonModel` class to a worker class that inherits [`mosec.Worker`](mosec.worker.Worker)
- move the `initialize` method to the `__init__` method in the new class
- move the `execute` method to the `forward` method in the new class
- if you still prefer to use the `auto_complete_config` method, you can merge it into the `__init__` method
- `mosec` doesn't have the corresponding `finalize` method as an unloading handler
- `mosec` doesn't require any special model directories or configurations
- to run multiple replicas, configure the `num` in [`append_worker`](mosec.server.Server.append_worker)

### `PyTriton`

- move the model loading logic to the `__init__` method, since this happens in a different process
- move the `infer_func` function to the `forward` method
