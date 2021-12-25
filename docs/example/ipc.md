This is an example demonstrating how you can enable the plasma shared memory store or customize your own IPC wrapper.

Mosec's multi-stage pipeline requires the output data from the previous stage to be transferred to the next stage across python processes. This is coordinated via Unix domain socket between every Python worker process from all stages and the Rust controller process.

By default, we serialize the data and directly transfer the bytes over the socket. However, users may find wrapping this IPC useful or more efficient for specific use cases. Therefore, we provide the `mosec.plugins.IPCWrapper` interface and an example implementation `PlasmaShmWrapper` based on [`pyarrow.plasma`](https://arrow.apache.org/docs/python/plasma.html).

The additional subprocess can be registered as a daemon thus it will be checked by mosec regularly and trigger graceful shutdown when the daemon exits.

#### **`plasma_shm_ipc.py`**

```python
--8<-- "examples/plasma_shm_ipc.py"
```

#### Start

    python plasma_shm_ipc.py

#### Test

    curl -X POST http://127.0.0.1:8000/inference -d '{"size": 100}'
