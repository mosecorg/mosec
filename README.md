<p align="center">
  <img src="https://user-images.githubusercontent.com/38581401/134487662-49733d45-2ba0-4c19-aa07-1f43fd35c453.png" height="230" alt="MOSEC" />
</p>

<p align="center">
  <a href="https://pypi.org/project/mosec/">
      <img src="https://badge.fury.io/py/mosec.svg" alt="PyPI version" height="20">
  </a>
  <a href="https://pepy.tech/project/mosec">
      <img src="https://pepy.tech/badge/mosec/month" alt="PyPi Downloads" height="20">
  </a>
  <a href="https://tldrlegal.com/license/apache-license-2.0-(apache-2.0)">
      <img src="https://img.shields.io/pypi/l/mosec" alt="License" height="20">
  </a>
  <a href="https://github.com/mosecorg/mosec/actions/workflows/check.yml?query=workflow%3A%22lint+and+test%22+branch%3Amain">
      <img src="https://github.com/mosecorg/mosec/actions/workflows/check.yml/badge.svg?branch=main" alt="Check status" height="20">
  </a>
</p>

<p align="center">
  <i>Model Serving made Efficient in the Cloud.</i>
</p>


## Introduction
Mosec is a high-performance and flexible model serving framework for building ML model-enabled backends and microservices. It bridges the gap between any machine learning models you just trained and the efficient online service API.

* **Highly performant**: web layer and task coordination built with Rust 🦀, which offers blazing speed in addition to efficient CPU utilization powered by async I/O
* **Ease of use**: user interface purely in Python 🐍, by which users can serve their models in an ML framework-agnostic manner using the same code as they do for offline testing
* **Dynamic batching**: aggregate requests from different users for batched inference and distribute results back
* **Pipelined stages**: spawn multiple processes for pipelined stages to handle CPU/GPU/IO mixed workloads


## Installation
Mosec requires Python 3.6 or above. Install the latest PyPI package with:

    pip install -U mosec


## Usage
### Write the server
Import the libraries and setup a basic logger to better observe what happens:
```python
import logging

from pydantic import BaseModel  # we need this to define our input/output schemas

from mosec import Server, Worker

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    "%(asctime)s - %(process)d - %(levelname)s - %(filename)s:%(lineno)s - %(message)s"
)
sh = logging.StreamHandler()
sh.setFormatter(formatter)
logger.addHandler(sh)
```


Define our service schemas for both input and output. These schemas will help us for data validation:
```python
class Request(BaseModel):
    x: float


class Response(BaseModel):
    y: float
```


Now, we are going to **build an API** to calculate the exponential with base **e** for a given number. To achieve that, we simply inherit the `Worker` class and override the `forward` method:
```python
import math


class CalculateExp(Worker):
    def forward(self, req: Request):
        y = math.exp(req.x)  # f(x) = e ^ x
        logger.debug(f"e ^ {req.x} = {y}")
        return Response(y=y)
```


Finally, we run the server when the file is executed:
```python
if __name__ == "__main__":
    server = Server(Request, Response)
    server.append_worker(
        CalculateExp, num=2
    )  # we spawn two processes for our calculator
    server.run()

```

### Run the server
After merging the snippets above into a file named `server.py`, we can first have a look at the supported arguments:

    python server.py --help

Then let's start the server...

    python server.py

and test it:

    curl -X POST http://127.0.0.1:8000/inference -d '{"x": 2}'

That's it! You have just hosted your ***exponential-computing model*** as a server! 😉

## Example
More ready-to-use examples can be found in the [Example](https://mosecorg.github.io/mosec/example) section.


## Contributing
We welcome any kind of contributions. Please give us feedback by raising issues or directly [contribute](https://mosecorg.github.io/mosec/contributing) your code and pull request!
