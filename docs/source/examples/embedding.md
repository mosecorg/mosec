# OpenAI compatible embedding service

This example shows how to create an embedding service that is compatible with the [OpenAI API](https://platform.openai.com/docs/api-reference/embeddings).

In this example, we use the embedding model from [Hugging Face LeaderBoard](https://huggingface.co/spaces/mteb/leaderboard).


## Server

```bash
EMB_MODEL=thenlper/gte-base python examples/embedding/server.py
```

```{include} ../../../examples/embedding/server.py
:code: python
```

## Client

```bash
EMB_MODEL=thenlper/gte-base python examples/embedding/client.py
```

```{include} ../../../examples/embedding/client.py
:code: python
```
