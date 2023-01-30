<p align="center">
  <img src="https://user-images.githubusercontent.com/38581401/134487662-49733d45-2ba0-4c19-aa07-1f43fd35c453.png" height="230" alt="MOSEC" />
</p>

<p align="center">
  <a href="https://discord.gg/Jq5vxuH69W">
    <img alt="discord invitation link" src="https://dcbadge.vercel.app/api/server/Jq5vxuH69W?style=flat">
  </a>
  <a href="https://pypi.org/project/mosec/">
    <img src="https://badge.fury.io/py/mosec.svg" alt="PyPI version" height="20">
  </a>
  <a href="https://pypi.org/project/mosec">
    <img src="https://img.shields.io/pypi/pyversions/mosec" alt="Python Version" />
  </a>
  <a href="https://pepy.tech/project/mosec">
    <img src="https://pepy.tech/badge/mosec/month" alt="PyPi Downloads" height="20">
  </a>
  <a href="https://tldrlegal.com/license/apache-license-2.0-(apache-2.0)">
    <img src="https://img.shields.io/github/license/mosecorg/mosec" alt="License" height="20">
  </a>
  <a href="https://github.com/mosecorg/mosec/actions/workflows/check.yml?query=workflow%3A%22lint+and+test%22+branch%3Amain">
    <img src="https://github.com/mosecorg/mosec/actions/workflows/check.yml/badge.svg?branch=main" alt="Check status" height="20">
  </a>
</p>

<p align="center">
  <i>Model Serving made Efficient in the Cloud.</i>
</p>

## Introduction

Mosec is a high-performance and flexible model serving framework for building ML model-enabled backend and microservices. It bridges the gap between any machine learning models you just trained and the efficient online service API.

- **Highly performant**: web layer and task coordination built with Rust 🦀, which offers blazing speed in addition to efficient CPU utilization powered by async I/O
- **Ease of use**: user interface purely in Python 🐍, by which users can serve their models in an ML framework-agnostic manner using the same code as they do for offline testing
- **Dynamic batching**: aggregate requests from different users for batched inference and distribute results back
- **Pipelined stages**: spawn multiple processes for pipelined stages to handle CPU/GPU/IO mixed workloads
- **Cloud friendly**: designed to run in the cloud, with the model warmup, graceful shutdown, and Prometheus monitoring metrics, easily managed by Kubernetes or any container orchestration systems
- **Do one thing well**: focus on the online serving part, users can pay attention to the model performance and business logic

## Installation

Mosec requires Python 3.7 or above. Install the latest [PyPI package](https://pypi.org/project/mosec/) with:

```shell
> pip install -U mosec
```

## Usage

### Write the server

Import the libraries and set up a basic logger to better observe what happens.

```python
import logging

from mosec import Server, Worker
from mosec.errors import ValidationError

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    "%(asctime)s - %(process)d - %(levelname)s - %(filename)s:%(lineno)s - %(message)s"
)
sh = logging.StreamHandler()
sh.setFormatter(formatter)
logger.addHandler(sh)
```

Then, we **build an API** to calculate the exponential with base **e** for a given number. To achieve that, we simply inherit the `Worker` class and override the `forward` method. Note that the input `req` is by default a JSON-decoded object, e.g., a dictionary here (wishfully it receives data like `{"x": 1}`). We also enclose the input parsing part with a `try...except...` block to reject invalid input (e.g., no key named `"x"` or field `"x"` cannot be converted to `float`).

```python
import math


class CalculateExp(Worker):
    def forward(self, req: dict) -> dict:
        try:
            x = float(req["x"])
        except KeyError:
            raise ValidationError("cannot find key 'x'")
        except ValueError:
            raise ValidationError("cannot convert 'x' value to float")
        y = math.exp(x)  # f(x) = e ^ x
        logger.debug(f"e ^ {x} = {y}")
        return {"y": y}
```

Finally, we append the worker to the server to construct a `single-stage workflow`, and we specify the number of processes we want it to run in parallel. Then we run the server.

```python
if __name__ == "__main__":
    server = Server()
    server.append_worker(
        CalculateExp, num=2
    )  # we spawn two processes for parallel computing
    server.run()

```

### Run the server

After merging the snippets above into a file named `server.py`, we can first have a look at the command line arguments:

```shell
> python server.py --help
```

Then let's start the server...

```shell
> python server.py
```

and in another terminal, test it:

```console
> curl -X POST http://127.0.0.1:8000/inference -d '{"x": 2}'
{
  "y": 7.38905609893065
}

> curl -X POST http://127.0.0.1:8000/inference -d '{"input": 2}' # wrong schema
validation error: cannot find key 'x'
```

or check the metrics:

```shell
> curl http://127.0.0.1:8000/metrics
```

For more debug logs, you can enable it by changing the Python & Rust log level:

```python
logger.setLevel(logging.DEBUG)
```

```shell
> RUST_LOG=debug python server.py
```

That's it! You have just hosted your **_exponential-computing model_** as a server! 😉

## Example

More ready-to-use examples can be found in the [Example](https://mosecorg.github.io/mosec/example) section. It includes:

- Multi-stage workflow
- Batch processing worker
- Shared memory IPC
- Customized GPU allocation
- Jax jitted inference
- PyTorch deep learning models:
  - sentiment analysis
  - image recognition
  - stable diffusion

## Contributing

We welcome any kind of contribution. Please give us feedback by [raising issues](https://github.com/mosecorg/mosec/issues/new/choose) or discussing on [Discord](https://discord.gg/Jq5vxuH69W). You could also directly [contribute](https://mosecorg.github.io/mosec/contributing) your code and pull request!

To start develop, you can use [envd](https://github.com/tensorchord/envd) to create an isolated and clean Python & Rust environment. Check the [envd-docs](https://envd.tensorchord.ai/) or [build.envd](./build.envd) for more information.

## Qualitative Comparison<sup>\*</sup>

|                                                             | Batcher | Pipeline | Parallel | I/O Format<sup>(1)</sup>                                                                                                                    | Framework<sup>(2)</sup> | Backend | Activity                                                                      |
| ----------------------------------------------------------- | :-----: | :------: | :------: | ------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------- | ------- | ----------------------------------------------------------------------------- |
| [TF Serving](https://github.com/tensorflow/serving)         |    ✅    |    ✅     |    ✅     | Limited<a href="https://github.com/tensorflow/serving/blob/master/tensorflow_serving/g3doc/api_rest.md#request-format-1"><sup>(a)</sup></a> | Heavily TF              | C++     | ![](https://img.shields.io/github/last-commit/tensorflow/serving)             |
| [Triton](https://github.com/triton-inference-server/server) |    ✅    |    ✅     |    ✅     | Limited                                                                                                                                     | Multiple                | C++     | ![](https://img.shields.io/github/last-commit/triton-inference-server/server) |
| [MMS](https://github.com/awslabs/multi-model-server)        |    ✅    |    ❌     |    ✅     | Limited                                                                                                                                     | Heavily MX              | Java    | ![](https://img.shields.io/github/last-commit/awslabs/multi-model-server)     |
| [BentoML](https://github.com/bentoml/BentoML)               |    ✅    |    ❌     |    ❌     | Limited<a href="https://docs.bentoml.org/en/latest/concepts.html#api-function-return-value"><sup>(b)</sup></a>                              | Multiple                | Python  | ![](https://img.shields.io/github/last-commit/bentoml/BentoML)                |
| [Streamer](https://github.com/ShannonAI/service-streamer)   |    ✅    |    ❌     |    ✅     | Customizable                                                                                                                                | Agnostic                | Python  | ![](https://img.shields.io/github/last-commit/ShannonAI/service-streamer)     |
| [Flask](https://github.com/pallets/flask)<sup>(3)</sup>     |    ❌    |    ❌     |    ❌     | Customizable                                                                                                                                | Agnostic                | Python  | ![](https://img.shields.io/github/last-commit/pallets/flask)                  |
| **[Mosec](https://github.com/mosecorg/mosec)**              |    ✅    |    ✅     |    ✅     | Customizable                                                                                                                                | Agnostic                | Rust    | ![](https://img.shields.io/github/last-commit/mosecorg/mosec)                 |


<sup>\*As accessed on 08 Oct 2021. By no means is this comparison showing that other frameworks are inferior, but rather it is used to illustrate the trade-off. The information is not guaranteed to be absolutely accurate. Please let us know if you find anything that may be incorrect.</sup>

<sup>**(1)**: Data format of the service's request and response. "Limited" in the sense that the framework has pre-defined requirements on the format.</sup>
<sup>**(2)**: Supported machine learning frameworks. "Heavily" means the serving framework is designed towards a specific ML framework. Thus it is hard, if not impossible, to adapt to others. "Multiple" means the serving framework provides adaptation to several existing ML frameworks. "Agnostic" means the serving framework does not necessarily care about the ML framework. Hence it supports all ML frameworks (in Python).</sup>
<sup>**(3)**: Flask is a representative of general purpose web frameworks to host ML models.</sup>
