# Multi-Route

This example shows how to use the multi-route feature.

You will need this feature if you want to:

- Serve multiple models in one service on different endpoints.
  - i.e. register `/embedding` & `/classify` with different models
- Serve one model to multiple different endpoints in one service.
  - i.e. register LLaMA with `/inference` and `/v1/chat/completions` to make it compatible with the OpenAI API
- Share a worker in different routes
  - The shared worker will collect the dynamic batch from multiple previous stages.
  - If you want to have multiple runtimes with sharing, you can declare multiple runtime instances with the same worker class.

The worker definition part is the same as for a single route. The only difference is how you register the worker with the server.

Here we expose a new [concept](../reference/concept.md) called [`Runtime`](mosec.runtime.Runtime).

You can create the `Runtime` and register on the server with a `{endpoint: [Runtime]}` dictionary.

See the complete demo code below. This will run a service with two endpoints:

- `/inference` with `Preprocess` and `Inference`
- `/v1/inference` with `TypedProcess`, `Inference` and `TypedPostprocess`

And the `Inference` worker is shared between the two routes.

## Server

<details>
<summary>multi_route_server.py</summary>

```{include} ../../../examples/multi_route/server.py
:code: python
```

</details>

## Client

<details>
<summary>multi_route_client.py</summary>

```{include} ../../../examples/multi_route/client.py
:code: python
```

</details>
