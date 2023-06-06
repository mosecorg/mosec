# Shared Memory IPC

This is an example demonstrating how you can enable the plasma shared memory store or customize your own IPC wrapper.

Mosec's multi-stage pipeline requires the output data from the previous stage to be transferred to the next stage across python processes. This is coordinated via Unix domain socket between every Python worker process from all stages and the Rust controller process.

By default, we serialize the data and directly transfer the bytes over the socket. However, users may find wrapping this IPC useful or more efficient for specific use cases. Therefore, we provide an example implementation `PlasmaShmIPCMixin` based on [`pyarrow.plasma`](https://arrow.apache.org/docs/11.0/python/plasma.html) and `RedisShmIPCMixin` based on [`redis`](https://pypi.org/project/redis). We recommend using `RedisShmWrapper` for better performance and longer-lasting updates.

```{warning}
`plasma` is deprecated. Please use Redis instead.
```

The additional subprocess can be registered as a daemon thus it will be checked by mosec regularly and trigger graceful shutdown when the daemon exits.

## **`plasma_shm_ipc.py`**

```{include} ../../../examples/plasma_shm_ipc.py
:code: python
```
## **`redis_shm_ipc.py`**

```{include} ../../../examples/redis_shm_ipc.py
:code: python
```

## Start

```shell
python plasma_shm_ipc.py
```

or

```shell
python redis_shm_ipc.py
```
## Test

```shell
http :8000/inference size=100
```
