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

from http import HTTPStatus

import httpx
import msgpack  # type: ignore

req = {
    "bin": b"hello mosec",
    "name": "type check",
}

resp = httpx.post("http://127.0.0.1:8000/inference", content=msgpack.packb(req))
if resp.status_code == HTTPStatus.OK:
    print(f"OK: {msgpack.unpackb(resp.content)}")
else:
    print(f"err[{resp.status_code}] {resp.text}")
