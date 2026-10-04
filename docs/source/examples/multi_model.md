# Multi-Model Serving

MOSEC supports serving multiple models from a single worker process via the
`MultiModelWorker` base class. Models are loaded on demand and cached in memory
with [SIEVE](https://sievecache.com) eviction — a simple, scan-resistant policy
that requires no reordering on cache hit.

Each request carries a `model_id` field. The worker groups incoming batches by
`model_id`, dispatches per-model sub-batches to `forward_model`, and manages
loading / evicting models transparently.

## YOLO Multi-Model

This example serves multiple YOLO model variants (e.g. different fine-tunes for
different object classes) from a single endpoint.

### **`examples/yolo26_multi_model/server.py`**

```{include} ../../../examples/yolo26_multi_model/server.py
:code: python
```

### Start

```shell
python examples/yolo26_multi_model/server.py
```

### Test

```shell
curl -X POST http://127.0.0.1:8000/inference \
     -H 'Content-Type: application/json' \
     -d '{"model_id": "yolo26n", "image_url": "https://example.com/img.jpg"}'
```

## Multi-LoRA Adapter

This example shows how to serve a base model with multiple LoRA adapters swapped
in and out on demand. The base model stays in memory permanently; only the
adapter weights are cached and evicted.

### **`examples/lora_multi_adapter/server.py`**

```{include} ../../../examples/lora_multi_adapter/server.py
:code: python
```

### Start

```shell
python examples/lora_multi_adapter/server.py
```

### Test

```shell
curl -X POST http://127.0.0.1:8000/inference \
     -H 'Content-Type: application/json' \
     -d '{"model_id": "lora-chat-v2", "prompt": "Hello, how are you?"}'
```
