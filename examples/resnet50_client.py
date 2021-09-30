import base64

import httpx  # type: ignore

dog_bytes = httpx.get(
    "https://raw.githubusercontent.com/pytorch/hub/master/images/dog.jpg"
).content


prediction = httpx.post(
    "http://localhost:8000/inference",
    json={"image": base64.b64encode(dog_bytes).decode()},
)
if prediction.status_code == 200:
    print(prediction.json())
else:
    print(prediction.status_code, prediction.content)
