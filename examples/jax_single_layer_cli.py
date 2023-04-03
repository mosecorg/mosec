# Copyright 2023 MOSEC Authors
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
"""Example: Client of the Jax server."""

import random

import httpx

input_data = [random.randint(-99, 99), random.randint(-99, 99), random.randint(-99, 99)]
print("Client : sending data : ", input_data)

prediction = httpx.post(
    "http://127.0.0.1:8000/inference",
    json={"array": input_data},
)
if prediction.status_code == 200:
    print(prediction.json())
else:
    print(prediction.status_code, prediction.json())
