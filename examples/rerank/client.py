# Copyright 2024 MOSEC Authors
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
import msgspec

req = {
    "query": "talk is cheap, show me the code",
    "docs": [
        "what a nice day",
        "life is short, use python",
        "early bird catches the worm",
    ],
}

resp = httpx.post(
    "http://127.0.0.1:8000/inference", content=msgspec.msgpack.encode(req)
)
if resp.status_code == HTTPStatus.OK:
    print(f"OK: {msgspec.msgpack.decode(resp.content)}")
else:
    print(f"err[{resp.status_code}] {resp.text}")
