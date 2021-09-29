Here are some out-of-the-box model servers powered by mosec for [PyTorch](https://pytorch.org/) users. We use the version 1.9.0 in the following examples.


## Natural Language Processing
Natural language processing model servers usually receive text data and make predictions ranging from text classification, question answering to translation and text generation.

### Sentiment Analysis
This server receives a string and predicts how positive its content is. We build the model server based on [Transformers](https://github.com/huggingface/transformers) of version 4.11.0.

We show how to customize the `deserialize` method of the ingress stage (`Preprocess`) and the `serialize` method of the egress stage (`Inference`). In this way, we can enjoy the high flexibility, directly reading data bytes from request body and writing the results into response body.

Note that in a stage that enables batching (e.g. `Inference` in this example), its worker's `forward` method deals with a list of data, while its `serialize` and `deserialize` methods only need to manipulate individual datum.

##### Server
    python distil_bert_sentiment.py
<details>
<summary>distil_bert_sentiment.py</summary>
```python
--8<-- "examples/distil_bert_server_pytorch.py"
```
</details>

##### Client
    curl -X POST http://127.0.0.1:8000/inference -d 'i bought this product for many times, highly recommend'


## Computer Vision
Computer vision model servers usually receive images or links to the images (downloading from the link becomes an I/O workload then), feed the preprocessed image data into the model and extract information like categories, bounding boxes and pixel labels as results.

### Image Recognition
This server receives an image and classify it according to the [ImageNet](https://www.image-net.org/) categorization. We specifically use [ResNet](https://arxiv.org/abs/1512.03385) as an image classifier and build a model service based on it. Nevertheless, this file serves as the starter code for any kind of image recognition model server.

We enable multiprocessing for `Preprocess` stage, so that it can produce enough tasks for `Inference` stage to do **batch inference**, which better exploits the GPU computing power. More interestingly, we also started multiple model by setting the number of worker for `Inference` stage to 2. This is because a single model is hard to fully occupy the GPU memory or utilization. Multiple models running on the same device in parallel can further increase our service throughput.

We also demonstrate how to build more proper **validation** through this example. In short, we can raise `ValidationError` whenever our validation check fails. This status will be finally returned to our clients as [HTTP 422](https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/422). We use [pydantic](https://pydantic-docs.helpmanual.io/) as a third-party tool for this purpose.

##### Server
    python resnet50_server.py
<details>
<summary>resnet50_server.py</summary>
```python
--8<-- "examples/resnet50_server_pytorch.py"
```
</details>

##### Client
    python resnet50_client.py
<details>
<summary>resnet50_client.py</summary>
```python
--8<-- "examples/resnet50_client.py"
```
</details>
