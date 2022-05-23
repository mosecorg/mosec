This is an example demonstrating how to give different worker processes customized environment variables to control things like GPU device allocation, etc.

Assume your machine has 4 GPUs, and you hope to deploy your model to all of them to handle inference requests in parallel, maximizing your service's throughput. With MOSEC, we provide parallel workers with customized environment variables to satisfy the needs.

As shown in the codes below, we can define our inference worker together with a list of environment variable dictionaries, each of which will be passed to the corresponding worker process. For example, if we set `CUDA_VISIBLE_DEVICES` to `0-3`, (the same copy of) our model will be deployed on 4 different GPUs and be queried in parallel, largely improving the system's throughput. You could verify this either from the server logs or the client response.

#### **`custom_env.py`**

```python
--8<-- "examples/custom_env.py"
```

#### Start

    python custom_env.py

#### Test

    curl -X POST http://127.0.0.1:8000/inference -d '{"dummy": 0}'
