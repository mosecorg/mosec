# Compression

This example demonstrates how to use the `--compression` feature for segmentation tasks. We use the example from the [Segment Anything Model 2](https://github.com/facebookresearch/sam2/blob/main/notebooks/image_predictor_example.ipynb). The request includes an image and its low resolution mask, the response is the final mask. Since there are lots of duplicate values in the mask, we can use `gzip`  or `zstd` to compress it.

## Server

```shell
python examples/segment/server.py --compression
```

<details>
<summary>segment.py</summary>

```{include} ../../../examples/segment/server.py
:code: python
```

</details>

## Client

```shell
python examples/segment/client.py
```

<details>
<summary>segment.py</summary>

```{include} ../../../examples/segment/client.py
:code: python
```

</details>
