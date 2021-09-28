Here are some out-of-the-box model servers powered by mosec for [PyTorch](https://pytorch.org/) users. We use the version 1.9.0 in the following examples.

## Computer Vision
Computer vision model servers usually receive images or links to the images (downloading from the link becomes an I/O workload then), feed the preprocessed image data into the model and extract information like categories, bounding boxes and pixel labels as results.
### Image Recognition
This server receives an image and classify it according to the [ImageNet](https://www.image-net.org/) categorization. We specifically use [ResNet](https://arxiv.org/abs/1512.03385) as an image classifier and build a model service based on it. Nevertheless, this file serves as the starter code for any kind of image recognition model server.

We enable multiprocessing for `Preprocess` stage, so that it can produce enough tasks for `Inference` stage to do **batch inference**, which better exploits the GPU computing power.
<details>
<summary>resnet50_server.py</summary>
```python
--8<-- "examples/resnet50_server_pytorch.py"
```
</details>
<details>
<summary>resnet50_client.py</summary>
```python
--8<-- "examples/resnet50_client.py"
```
</details>



## Natural Language Processing
Natural language processing model servers usually receive text data and make predictions ranging from text classification, question answering to translation and text generation.
### Sentiment Analysis
This server receives a string and predicts how positive its content is. We build the model server based on [Transformers](https://github.com/huggingface/transformers) of version 4.11.0.

We customize the `deserialize` method of the ingress stage and the `serialize` method of the egress stage. In this way, we directly manipulate the data bytes in request data with high flexibility, and write the results into response body.
<details>
<summary>distil_bert_sentiment.py</summary>
```python
--8<-- "examples/distil_bert_server_pytorch.py"
```
</details>

    curl -X POST http://127.0.0.1:8000/inference -d 'i  bought this product for many times, highly recommend'
