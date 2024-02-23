# Cross-Encoder model for reranking

This example shows how to use a cross-encoder model to rerank a list of passages based on a query. This is useful for hybrid search that combines multiple retrieval results.


## Server

```bash
python examples/rerank/server.py
```

```{include} ../../../examples/rerank/server.py
:code: python
```

## Client

```bash
python examples/rerank/client.py
```

```{include} ../../../examples/rerank/client.py
:code: python
```
