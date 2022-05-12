# Copyright 2022 MOSEC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
