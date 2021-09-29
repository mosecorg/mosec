An echo server is usually the very first server you wanna implement to get familiar with the framework.

This server sleeps for a given period of time and return. It is a simple illustration of how **multi-stage workload** is implemented. It also shows how to write a simple **validation** for input data.

#### **`echo.py`**
```python
--8<-- "examples/echo.py"
```

#### Start

    python echo.py

#### Test

    http :8000/inference time=1.5
