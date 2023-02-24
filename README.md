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
- **Do one thing well**: focus on the online serving part, users can pay attention to the model optimization and business logic

## Installation

Mosec requires Python 3.7 or above. Install the latest [PyPI package](https://pypi.org/project/mosec/) with:

```shell
pip install -U mosec
```

## Usage

We demonstrate how Mosec can easily host a pre-trained stable diffusion model as a service. You need to install [diffusers](https://github.com/huggingface/diffusers) and [transformers](https://github.com/huggingface/transformers) as prerequisites:

```shell
pip install --upgrade diffusers[torch] transformers
```

### Write the server

Firstly, we import the libraries and set up a basic logger to better observe what happens.

```python
from io import BytesIO
from typing import List

import torch  # type: ignore
from diffusers import StableDiffusionPipeline  # type: ignore

from mosec import Server, Worker, get_logger
from mosec.mixin import MsgpackMixin

logger = get_logger()
```

Then, we **build an API** for clients to query a text prompt and obtain an image based on the [stable-diffusion-v1-5 model](https://huggingface.co/runwayml/stable-diffusion-v1-5). To achieve that, we simply inherit the `Worker` and `MsgpackMixin` class, then initialize the model in the `__init__` method and override the `forward` method. By default, the input `data` of the `forward` method should be a JSON-decoded object. Using `MsgpackMixin` will override it to use the faster and smaller [msgpack](https://msgpack.org/index.html) for both request and response data. In this example, the `forward` method will wishfully receive a _list_ of string, e.g., `['a cute cat playing with a red ball', 'a man sitting in front of a computer', ...]`, aggregated from different clients for _batch inference_, improving the system throughput. Also note that the returned objects will be encoded by the msgpack protocol as well, due to the use of `MsgpackMixin`.

```python
class StableDiffusion(MsgpackMixin, Worker):
    def __init__(self):
        self.pipe = StableDiffusionPipeline.from_pretrained(
            "runwayml/stable-diffusion-v1-5", torch_dtype=torch.float16
        )
        device = "cuda" if torch.cuda.is_available() else "cpu"
        self.pipe = self.pipe.to(device)
        self.example = ["useless example prompt"] * 4  # warmup (bs=4)

    def forward(self, data: List[str]) -> List[memoryview]:
        logger.debug("generate images for %s", data)
        res = self.pipe(data)
        logger.debug("NSFW: %s", res[1])
        images = []
        for img in res[0]:
            dummy_file = BytesIO()
            img.save(dummy_file, format="JPEG")
            images.append(dummy_file.getbuffer())
        return images
```

Finally, we append the worker to the server to construct a *single-stage* workflow (multiple stages can be [pipelined](https://en.wikipedia.org/wiki/Pipeline_(computing)) to further boost the throughput, see [this example](https://mosecorg.github.io/mosec/example/pytorch/#computer-vision)), and specify the number of processes we want it to run in parallel (`num=1`), and the maximum batch size (`max_batch_size=4`, the maximum number of requests dynamic batching will accumulate before timeout; timeout is defined with the flag `--wait` in milliseconds, meaning the longest time Mosec waits until sending the batch to the Worker).

```python
if __name__ == "__main__":
    server = Server()
    # 1) `num` specify the number of processes that will be spawned to run in parallel.
    # 2) By configuring the `max_batch_size` with the value > 1, the input data in your
    # `forward` function will be a list (batch); otherwise, it's a single item.
    server.append_worker(StableDiffusion, num=1, max_batch_size=4)
    server.run()
```

### Run the server

The above snippets are merged in our example file. You may directly run at the project root level. We first have a look at the _command line arguments_ (explanations [here](https://mosecorg.github.io/mosec/argument/)):

```shell
python examples/stable_diffusion/server.py --help
```

Then let's start the server with debug logs:

```shell
python examples/stable_diffusion/server.py --debug
```

And in another terminal, test it:

```shell
python examples/stable_diffusion/client.py --prompt "a cute cat playing with a red ball" --output cat.jpg --port 8000
```

You will get an image named "cat.jpg" in the current directory.

You can check the metrics:

```shell
curl http://127.0.0.1:8000/metrics
```

That's it! You have just hosted your **_stable-diffusion model_** as a service! 😉

## Examples

More ready-to-use examples can be found in the [Example](https://mosecorg.github.io/mosec/example) section. It includes:

- [Multi-stage workflow demo](https://mosecorg.github.io/mosec/example/echo/): a simple echo demo even without any ML model.
- [Shared memory IPC](https://mosecorg.github.io/mosec/example/ipc/): inter-process communication with shared memory.
- [Customized GPU allocation](https://mosecorg.github.io/mosec/example/env/): deploy multiple replicas, each using different GPUs.
- [Customized metrics](https://mosecorg.github.io/mosec/example/metric/): record your own metrics for monitoring.
- [Jax jitted inference](https://mosecorg.github.io/mosec/example/jax/): just-in-time compilation speeds up the inference.
- PyTorch deep learning models:
  - [sentiment analysis](https://mosecorg.github.io/mosec/example/pytorch/#natural-language-processing): infer the sentiment of a sentence.
  - [image recognition](https://github.com/mosecorg/mosec/blob/main/examples/resnet50_server_msgpack.py): categorize a given image.
  - [stable diffusion](https://github.com/mosecorg/mosec/tree/main/examples/stable_diffusion): generate images based on texts, with msgpack serialization.

## Configuration

- Dynamic batching
  - `max_batch_size` is configured when you `append_worker` (make sure inference with the max value won't cause the out-of-memory in GPU).
  - `--wait (default=10ms)` is configured through CLI arguments (this usually should <= one batch inference duration).
  - If enabled, it will collect a batch either when it reaches the `max_batch_size` or the `wait` time.
- Check the [arguments doc](https://mosecorg.github.io/mosec/argument/).

## Deployment

- This may require some shared memory, remember to set the `--shm-size` flag if you are using docker.
- This service doesn't require Gunicorn or NGINX, but you can certainly use the ingress controller. BTW, it should be the PID 1 process in the container since it controls multiple processes.
- Remember to collect the **metrics**.
  - `mosec_service_batch_size_bucket` shows the batch size distribution.
  - `mosec_service_process_duration_second_bucket` shows the duration for each stage (excluding the IPC time).
  - `mosec_service_remaining_task` shows the number of currently processing tasks.
  - `mosec_service_throughput` shows the service throughput.
- Stop the service with `SIGINT` or `SIGTERM` since it has the graceful shutdown logic.

## Contributing

We welcome any kind of contribution. Please give us feedback by [raising issues](https://github.com/mosecorg/mosec/issues/new/choose) or discussing on [Discord](https://discord.gg/Jq5vxuH69W). You could also directly [contribute](https://mosecorg.github.io/mosec/contributing) your code and pull request!

To start develop, you can use [envd](https://github.com/tensorchord/envd) to create an isolated and clean Python & Rust environment. Check the [envd-docs](https://envd.tensorchord.ai/) or [build.envd](https://github.com/mosecorg/mosec/blob/main/build.envd) for more information.

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
