# Customized Metrics

This is an example demonstrating how to add your customized Python side Prometheus metrics.

Mosec already has the Rust side metrics, including:

* throughput for the inference endpoint
* duration for each stage (including the IPC time)
* batch size (only for the `max_batch_size > 1` workers)
* number of remaining tasks to be processed

If you need to monitor more details about the inference process, you can add some Python side metrics. E.g., the inference result distribution, the duration of some CPU-bound or GPU-bound processing, the IPC time (get from `rust_step_duration - python_step_duration`).

This example has a simple WSGI app as the monitoring metrics service. In each worker process, the `Counter` will collect the inference results and export them to the metrics service. For the inference part, it parses the batch data and compares them with the average value.

For more information about the multiprocess mode for the metrics, check the [Prometheus doc](https://github.com/prometheus/client_python#multiprocess-mode-eg-gunicorn).

## **`python_side_metrics.py`**

```{include} ../../../examples/python_side_metrics.py
:code: python
```

## Start

```shell
python python_side_metrics.py
```

## Test

```shell
http POST :8000/inference num=1
```

## Check the Python side metrics

```shell
http :8080
```

## Check the Rust side metrics

```shell
http :8000/metrics
```
