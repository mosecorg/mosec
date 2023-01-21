This example shows how to utilize the [Jax framework](https://github.com/google/jax) to build a just-in-time (JIT) compiled inference server. You could install Jax following their official guide and you also need `chex` to run this example (`pip install -U chex`).

We use a single layer neural network for this minimal example. You could also experiment the speedup of JIT by setting the environment variable `USE_JIT=true` and observe the latency difference. Note that in the `__init__` of the worker we set the `self.multi_examples` as a list of example inputs to warmup, because different batch sizes will trigger re-jitting when they are traced for the first time.

##### Server

    USE_JIT=true python jax_single_layer.py

<details>
<summary>jax_single_layer.py</summary>
```python
--8<-- "examples/jax_single_layer.py"
```
</details>

##### Client

    python jax_single_layer_cli.py

<details>
<summary>jax_single_layer_cli.py</summary>
```python
--8<-- "examples/jax_single_layer_cli.py"
```
</details>
