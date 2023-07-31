# Copyright 2023 MOSEC Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
from http import HTTPStatus

import httpx
import msgpack  # type: ignore

typed_req = {
    "bin": b"hello mosec with type check",
    "name": "type check",
}

print(">> requesting for the typed route with msgpack serde")
resp = httpx.post(
    "http://127.0.0.1:8000/v1/inference", content=msgpack.packb(typed_req)
)
if resp.status_code == HTTPStatus.OK:
    print(f"OK: {msgpack.unpackb(resp.content)}")
else:
    print(f"err[{resp.status_code}] {resp.text}")

print(">> requesting for the untyped route with json serde")
resp = httpx.post("http://127.0.0.1:8000/inference", content=b"hello mosec")
if resp.status_code == HTTPStatus.OK:
    print(f"OK: {json.loads(resp.content)}")
else:
    print(f"err[{resp.status_code}] {resp.text}")
