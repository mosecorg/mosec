from __future__ import annotations
from functools import partial

import gc
import pickle
import traceback
from dataclasses import dataclass
from io import BytesIO
from time import perf_counter, sleep
from typing import Any, List
import numpy as np


import redis
from pyarrow import plasma


class PlasmaShmWrapper:
    def __init__(self, shm_path: str) -> None:
        self.client = plasma.connect(shm_path)

    def _put_plasma(self, data: List[bytes]) -> List[plasma.ObjectID]:
        return [self.client.put(x) for x in data]

    def _get_plasma(self, object_ids: List[plasma.ObjectID]) -> List[bytes]:
        objects = self.client.get(object_ids)
        self.client.delete(object_ids)
        return objects

    def put(self, data: List[bytes]) -> List[bytes]:
        object_ids = self._put_plasma(data)
        return [id.binary() for id in object_ids]

    def get(self, ids: List[bytes]) -> List[bytes]:
        object_ids = [plasma.ObjectID(id) for id in ids]
        return self._get_plasma(object_ids)


class RedisWrapper:
    def __init__(self, url: str = "") -> None:
        self.client = redis.from_url(url)

    def put(self, data: List[bytes]) -> List[int]:
        ids = []
        for item in data:
            _id = self.client.incr("test")
            ids.append(_id)
            self.client.set(_id, item)
        return ids

    def get(self, object_ids: List[str]) -> List[bytes]:
        datas = []
        for id in object_ids:
            datas.append(self.client.get(id))
        self.client.delete(*object_ids)
        return datas


class RedisPipelineWrapper:
    """
    Redis Wrapper with batch-pipelined-incr and batch-pipelined-set.
    """

    def __init__(self, url: str = "") -> None:
        self.client = redis.from_url(url)

    def put(self, data: List[bytes]) -> List[int]:
        with self.client.pipeline() as p:
            for _ in range(len(data)):
                p.incr("test")
            ids = p.execute()
            for idx, id in enumerate(ids):
                p.set(id, data[idx])
            p.execute()
        return ids

    def get(self, object_ids: List[str]) -> List[bytes]:
        with self.client.pipeline() as p:
            for id in object_ids:
                p.get(id)
            p.delete(id, *object_ids)
            return p.execute()[: len(object_ids)]


class RedisPipelineWrapper2:
    """
    Redis Wrapper with pipelined-set-then-incr.
    """

    def __init__(self, url: str = "") -> None:
        self.client = redis.from_url(url)
        self.next_id = self.client.incr("test")

    def put(self, data: List[bytes]) -> List[int]:
        ids = []
        with self.client.pipeline() as p:
            for data in data:
                ids.append(self.next_id)
                p.set(self.next_id, data)
                p.incr("test")
                self.next_id = p.execute()[1]
        return ids

    def get(self, object_ids: List[str]) -> List[bytes]:
        with self.client.pipeline() as p:
            for id in object_ids:
                p.get(id)
            p.delete(id, *object_ids)
            return p.execute()[: len(object_ids)]


@dataclass(frozen=True)
class Data:
    arr: np.ndarray | dict
    msg: str
    epoch: int


def generate_data():
    return (
        Data(
            {"msg": "long message" * 1000, "vec": np.random.rand(1024)},
            "long message with 1024 vector",
            10,
        ),
        Data(
            {
                "int": 233,
                "float": 3.14,
                "vec": np.random.rand(1024),
                "matrix": np.random.rand(64, 1024),
            },
            "int, float, vector and matrix",
            10,
        ),
    )


def generate_np_data():
    return (
        Data(np.random.rand(1), "scalar", 100),
        Data(np.random.rand(1024), "vector", 100),
        Data(np.random.rand(64, 1024), "matrix", 100),
        Data(np.random.rand(3, 1024, 1024), "image", 10),
        Data(np.random.rand(64, 3, 1024, 1024), "batch of images", 5),
    )


def plasma_store(duplicate: int, data: Data):
    global plasam_client
    ids = plasam_client.put([pickle.dumps(data.arr)] * duplicate)
    plasam_client.get(ids)


def redis_s(redis_client: Any, duplicate: int, data: Data):
    ids = redis_client.put([pickle.dumps(data.arr)] * duplicate)
    redis_client.get(ids)


def time_record(func, data: Data, threshold=1):
    res = []
    total_sec = 0
    while total_sec < threshold:
        for _ in range(data.epoch):
            t0 = perf_counter()
            try:
                func(data)
            except:
                print(traceback.format_exc())
            finally:
                res.append(perf_counter() - t0)
                total_sec += res[-1]
    return res


def display_result(func, data):
    gc_flag = gc.isenabled()
    gc.disable()
    try:
        t = time_record(func, data)
    finally:
        if gc_flag:
            gc.enable()
    size = data.arr.size if isinstance(data.arr, np.ndarray) else "<unknown>"
    print(
        f"{func.__name__}\tsize: {size:9}\ttimes: "
        f"min({np.min(t):.5})\tmid({np.median(t):.5})\tmax({np.max(t):.5})\t"
        f"95%({np.percentile(t, 0.95):.5})\tStd.({np.std(t):.5})",
    )


def benchmark():
    unix_path = "/tmp/redis/redis.sock"
    tcp_path = "127.0.0.1:6379"
    with plasma.start_plasma_store(plasma_store_memory=10 * 1000 * 1000 * 1000) as (
        shm_path,
        proc,
    ):
        global plasam_client, redis_client, redis_pipeline_client, redis_pipeline_client2
        plasam_client = PlasmaShmWrapper(shm_path)
        redis_unix = RedisWrapper(f"unix://{unix_path}")
        redis_unix_pipe = RedisPipelineWrapper(f"unix://{unix_path}")
        redis_unix_pipe2 = RedisPipelineWrapper2(f"unix://{unix_path}")
        redis_tcp = RedisWrapper(f"redis://@{tcp_path}")
        redis_tcp_pipe = RedisPipelineWrapper(f"redis://@{tcp_path}")
        redis_tcp_pipe2 = RedisPipelineWrapper2(f"redis://@{tcp_path}")
        print(">>> benchmark for numpy array")

        funcs = []
        plasma_store.__name__ = plasma_store.__name__ + "\t"
        for duplicate in [1, 10]:
            redis_funcs = []
            for name, client in zip(
                [
                    "redis_unix\t",
                    "redis_unix_pipe",
                    "redis_unix_pipe2",
                    "redis_tcp\t",
                    "redis_tcp_pipe",
                    "redis_tcp_pipe2",
                ],
                [
                    redis_unix,
                    redis_unix_pipe,
                    redis_unix_pipe2,
                    redis_tcp,
                    redis_tcp_pipe,
                    redis_tcp_pipe2,
                ],
            ):
                f = partial(redis_s, client)
                f.__name__ = name
                redis_funcs.append(f)
            for f in [plasma_store, *redis_funcs]:
                fd = partial(f, duplicate)
                fd.__name__ = f"{f.__name__}*{duplicate}"
                funcs.append(fd)

        for data in generate_np_data():
            for func in funcs:
                display_result(func, data)

        print(">>> benchmark for normal data mixed with numpy array")
        for data in generate_data():
            print("=" * 120)
            for func in funcs:
                display_result(func, data)


if __name__ == "__main__":
    benchmark()
