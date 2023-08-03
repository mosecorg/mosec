# Concept and FAQs

There are a few terms used in `mosec`.

- `worker`: a Python process that executes the `forward` method (inherit from [`mosec.Worker`](mosec.worker.Worker))
- `stage`: one processing unit in the pipeline, each stage contains several `worker` replicas
  - also known as [`Runtime`](mosec.runtime.Runtime) in the code
  - each stage retrieves the data from the previous stage and passes the result to the next stage
  - retrieved data will be deserialized by the [`Worker.deserialize_ipc`](mosec.worker.Worker.deserialize_ipc) method
  - data to be passed will be serialized by the [`Worker.serialize_ipc`](mosec.worker.Worker.serialize_ipc) method
- `ingress/egress`: the first/last stage in the pipeline
  - ingress gets data from the client, while egress sends data to the client
  - data will be deserialized by the ingress [`Worker.serialize`](mosec.worker.Worker.serialize) method and serialized by the egress [`Worker.deserialize`](mosec.worker.Worker.deserialize) method
- `pipeline`: a chain of processing stages, will be registered to an endpoint (default: `/inference`)
  - a server can have multiple pipelines, check the [multi-route](../examples/multi_route.md) example
- `dynamic batching`: batch requests until either the max batch size or the max wait time is reached
- `controller`: a Rust tokio thread that works on:
  - read from the previous queue to get new tasks
  - send tasks to the ready-to-process worker via the Unix domain socket
  - receive results from the worker
  - send the tasks to the next queue

## FAQs

### How to raise an exception?

Use the `raise` keyword with [mosec.errors](mosec.errors). Raising other exceptions will be treated as an "500 Internal Server Error".

If a request raises any exception, the error will be returned to the client directly without going through the rest stages.

### How to change the serialization/deserialization methods?

Just let the ingress/egress worker inherit a suitable mixin like [`MsgpackMixin`](mosec.mixin.MsgpackMixin).

```{note}
The inheritance order matters in Python. Check [multiple inheritance](https://docs.python.org/3/tutorial/classes.html#multiple-inheritance) for more information.
```

You can also implement the `serialize/deserialize` method to your `ingress/egress` worker directly.

### How to share configurations among different workers?

If the configuration structure is initialized globally, all the workers should be able to use it directly.

If you want to assign different workers with different configurations, the best way is to use the `env` (ref [`append_worker`](mosec.server.Server.append_worker)).
