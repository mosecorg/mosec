Here are some out-of-the-box model servers powered by mosec for [PyTorch](https://pytorch.org/) users. We use the version 1.9.0 in the following examples.

## Computer Vision
Computer vision model servers usually receive images or links to the images (downloading from the link becomes an I/O workload then), feed the preprocessed image data into the model and extract information from the output results.
### Image Recognition
This server receives an image and classify it according to the [ImageNet](https://www.image-net.org/) categorization. We specifically use [ResNet](https://arxiv.org/abs/1512.03385) as an image classifier and build a model service based on it. Nevertheless, this file serves as the starter code for any kind of image recognition model server.

We enable multiprocessing for `Preprocess` stage, so that it can produce enough tasks for `Inference` stage to do **batch inference**, which better exploits the GPU computing power.
<details>
<summary>resnet50.py</summary>
```python
--8<-- "examples/resnet50_server_pytorch.py"
```
</details>

### Object Detection

### Image Segmentation
