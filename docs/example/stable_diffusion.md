This example provides a demo service for stable diffusion. You can develop this in the container environment by using [envd](https://github.com/tensorchord/envd): `envd up -p examples/stable_diffusion`.

You should be able to try this demo under the `mosec/examples/stable_diffusion/` directory.

##### Server

    envd build -t sd:serving
    docker run --rm --gpus all -p 8000:8000 sd:serving

```python
--8<-- "examples/stable_diffusion/server.py"
```

##### Client

    python client.py --prompt "a cute cat site on the basketball"

```python
--8<-- "examples/stable_diffusion/client.py"
```
