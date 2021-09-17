import base64

import httpx

dog_bytes = httpx.get(
    "https://raw.githubusercontent.com/pytorch/hub/master/images/dog.jpg"
).content


prediction = httpx.post(
    "http://localhost:8000/inference",
    json={"image": base64.b64encode(dog_bytes).decode()},
)
print(prediction.json())
