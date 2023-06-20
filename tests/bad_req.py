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

"""A chaos test that contains:

- normal request
- early disconnection
- client bad request data
- service internal error
"""

import concurrent.futures
import os
import shlex
import subprocess
from http import HTTPStatus
from random import random

import httpx

from tests.utils import wait_for_port_free, wait_for_port_open

PORT = 5934
URL = f"http://127.0.0.1:{PORT}/inference"
REQ_NUM = int(os.getenv("CHAOS_REQUEST", 10000))
# set the thread number in case the CI server cannot get the real CPU number.
THREAD = 8


def random_req(params, timeout):
    resp = httpx.post(URL, json=params, timeout=timeout)
    return resp


def main():
    with concurrent.futures.ThreadPoolExecutor(max_workers=THREAD) as e:
        futures = [
            e.submit(
                random_req,
                {"time": 0.1} if random() > 0.3 else {"hey": 0},
                random() / 3.0,
            )
            for _ in range(REQ_NUM)
        ]
        count = 0
        for future in concurrent.futures.as_completed(futures):
            try:
                data = future.result()
            except Exception as err:
                print("[x]", err)
            else:
                print("[~]", data)
                count += 1

    print(f">> {count}/{REQ_NUM} requests received before disconnection")

    # re-try to check if the service is still alive
    resp = httpx.post(URL, json={"time": 0})
    if resp.status_code != HTTPStatus.OK:
        print(resp)
        raise RuntimeError()


if __name__ == "__main__":
    service = subprocess.Popen(
        shlex.split(
            f"python tests/services/bad_service.py --debug --timeout 500 --port {PORT}"
        )
    )
    assert wait_for_port_open(port=PORT)
    try:
        main()
    finally:
        service.terminate()
    assert wait_for_port_free(port=PORT)
