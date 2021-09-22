<p align="center">
  <img src="./.github/static/logo_name.svg" height="150" alt="MOSEC" />
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
  <a href="https://github.com/facebookresearch/CompilerGym/actions?query=workflow%3ACI+branch%3Adevelopment">
      <img src="https://github.com/mosecorg/mosec/actions/workflows/check.yml/badge.svg" alt="Check status" height="20">
  </a>
</p>

<p align="center">
  <i>Model Serving made Efficient in the Cloud.</i>
</p>

## Introduction

Mosec is a high-performance and flexible model serving framework for building ML model enabled backends and microservices. It bridges the gap between any machine learning models you just trained and the efficient online service API.

* **Highly performant**: web layer and task coordination built with Rust 🦀, which offers blazing speed in addition to efficient CPU utilization powered by async I/O
* **Ease of use**: user interface purely in Python 🐍, by which users can serve their models in any ML framework using the same code as they do for offline testing
* **Dynamic batching**: aggregate requests from different users for batched inference and distribute results back
* **Pipelined stages**: spawn multiple processes for pipelined stages to handle CPU/GPU/IO mixed workloads

## Installation

Install the latest PyPI package with:

    pip install -U mosec

## Usage
Wanna spend only 5 minutes in converting your trained model into a service? Let's go.
```python
WIP
```

## Contributing
We welcome any kind of contributions. Please give us feedback by raising issues or directly [contribute your code and pull request](.github/CONTRIBUTING.md)!
