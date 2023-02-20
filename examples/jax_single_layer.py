# Copyright 2023 MOSEC Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Example: Simple jax jitted inference with a single layer classifier."""

import os
import time
from typing import List

import chex  # type: ignore
import jax  # type: ignore
import jax.numpy as jnp  # type: ignore

from mosec import Server, ValidationError, Worker, get_logger

logger = get_logger()

INPUT_SIZE = 3
LATENT_SIZE = 16
OUTPUT_SIZE = 2

MAX_BATCH_SIZE = 8
USE_JIT = os.environ.get("USE_JIT", "false")


class JittedInference(Worker):
    """Sample Class."""

    def __init__(self):
        super().__init__()
        key = jax.random.PRNGKey(42)
        k_1, k_2 = jax.random.split(key)
        self._layer1_w = jax.random.normal(k_1, (INPUT_SIZE, LATENT_SIZE))
        self._layer1_b = jnp.zeros(LATENT_SIZE)
        self._layer2_w = jax.random.normal(k_2, (LATENT_SIZE, OUTPUT_SIZE))
        self._layer2_b = jnp.zeros(OUTPUT_SIZE)

        # Enumerate all batch sizes for caching.
        self.multi_examples = []
        dummy_array = list(range(INPUT_SIZE))
        for i in range(MAX_BATCH_SIZE):
            self.multi_examples.append([{"array": dummy_array}] * (i + 1))

        if USE_JIT == "true":
            self.batch_forward = jax.jit(self._batch_forward)
        else:
            self.batch_forward = self._batch_forward

    def _forward(self, x_single: jnp.ndarray) -> jnp.ndarray:
        chex.assert_rank([x_single], [1])
        h_1 = jnp.dot(self._layer1_w.T, x_single) + self._layer1_b
        a_1 = jax.nn.relu(h_1)
        h_2 = jnp.dot(self._layer2_w.T, a_1) + self._layer2_b
        o_2 = jax.nn.softmax(h_2)
        return jnp.argmax(o_2, axis=-1)

    def _batch_forward(self, x_batch: jnp.ndarray) -> jnp.ndarray:
        chex.assert_rank([x_batch], [2])
        return jax.vmap(self._forward)(x_batch)

    def forward(self, data: List[dict]) -> List[dict]:
        time_start = time.perf_counter()
        try:
            input_array_raw = [ele["array"] for ele in data]
        except KeyError as err:
            raise ValidationError(f"cannot find key {err}") from err
        input_array = jnp.array(input_array_raw)
        output_array = self.batch_forward(input_array)
        output_category = output_array.tolist()
        elapse = time.perf_counter() - time_start
        return [{"category": c, "elapse": elapse} for c in output_category]


if __name__ == "__main__":
    server = Server()
    server.append_worker(JittedInference, max_batch_size=MAX_BATCH_SIZE)
    server.run()
