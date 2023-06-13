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
"""Example: Common Client for Test"""

import json
import sys
from http import HTTPStatus

import httpx

req = {
    "echo": {"time": 1.5},
    "plasma_shm_ipc": {"size": 100},
    "redis_shm_ipc": {"size": 100},
}


def post(data):
    """Post request to server"""
    resp = httpx.post("http://127.0.0.1:8000/inference", content=data)
    if resp.status_code == HTTPStatus.OK:
        print(f"OK: {resp.json()}")
    else:
        print(f"err[{resp.status_code}] {resp.text}")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Please specify a shm to run: plasma or redis")
        sys.exit(1)

    k = sys.argv[1]
    content = req[k]
    if k not in ["msgpack"]:
        content = json.dumps(content)
    post(content)
