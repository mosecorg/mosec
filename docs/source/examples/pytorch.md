# PyTorch Examples

Here are some out-of-the-box model servers powered by mosec for [PyTorch](https://pytorch.org/) users. We use the version 1.9.0 in the following examples.

## Natural Language Processing

Natural language processing model servers usually receive text data and make predictions ranging from text classification, question answering to translation and text generation.

### Sentiment Analysis

This server receives a string and predicts how positive its content is. We build the model server based on [Transformers](https://github.com/huggingface/transformers) of version 4.11.0.

We show how to customize the `deserialize` method of the ingress stage (`Preprocess`) and the `serialize` method of the egress stage (`Inference`). In this way, we can enjoy the high flexibility, directly reading data bytes from request body and writing the results into response body.

Note that in a stage that enables batching (e.g. `Inference` in this example), its worker's `forward` method deals with a list of data, while its `serialize` and `deserialize` methods only need to manipulate individual datum.

#### Server

```shell
python distil_bert_server_pytorch.py
```

<details>
<summary>distil_bert_server_pytorch.py</summary>

```{include} ../../../examples/distil_bert_server_pytorch.py
:code: python
```

</details>

#### Client

```shell
echo 'i bought this product for many times, highly recommend' | http POST :8000/inference
```

## Computer Vision

Computer vision model servers usually receive images or links to the images (downloading from the link becomes an I/O workload then), feed the preprocessed image data into the model and extract information like categories, bounding boxes and pixel labels as results.

### Image Recognition

This server receives an image and classify it according to the [ImageNet](https://www.image-net.org/) categorization. We specifically use [ResNet](https://arxiv.org/abs/1512.03385) as an image classifier and build a model service based on it. Nevertheless, this file serves as the starter code for any kind of image recognition model server.

We enable multiprocessing for `Preprocess` stage, so that it can produce enough tasks for `Inference` stage to do **batch inference**, which better exploits the GPU computing power. More interestingly, we also started multiple model by setting the number of worker for `Inference` stage to 2. This is because a single model hardly fully occupy the GPU memory or utilization. Multiple models running on the same device in parallel can further increase our service throughput.

When instantiating the `Server`, we enable `plasma_shm`, which utilizes the [`pyarrow.plasma`](https://arrow.apache.org/docs/11.0/python/plasma.html) as a shared memory data store for IPC. This could benefit the data transfer, especially when the data is large (preprocessed image data in this case). Note that you need to use `pip install -U pyarrow==11` to install necessary dependencies.

We also demonstrate how to customized **validation** on the data content through this example. In the `forward` method of the `Preprocess` worker, we firstly check the key of the input, then try to decode the str and load it into array. If any of these steps fails, we raise the `ValidationError`. The status will be finally returned to our clients as [HTTP 422](https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/422).

#### Server

```shell
python resnet50_server_msgpack.py
```

<details>
<summary>resnet50_server_msgpack.py</summary>

```{include} ../../../examples/resnet50_server_msgpack.py
:code: python
```

</details>

#### Client

```shell
python resnet50_client_msgpack.py
```

<details>
<summary>resnet50_client_msgpack.py</summary>

```{include} ../../../examples/resnet50_client_msgpack.py
:code: python
```

</details>
