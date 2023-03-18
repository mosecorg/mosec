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

import concurrent.futures
import random
import shlex
import subprocess
import time
from http import HTTPStatus

import httpx

URL = "http://localhost:8000/inference"
REQ_NUM = 10000


def random_req(params, timeout):
    resp = httpx.post(URL, json=params, timeout=timeout)
    return resp


def main():
    with concurrent.futures.ThreadPoolExecutor() as e:
        futures = [
            e.submit(random_req, {"time": 0.1}, random.random() / 5.0)
            for _ in range(REQ_NUM)
        ]
        count = 0
        for future in concurrent.futures.as_completed(futures):
            try:
                data = future.result()
            except Exception as err:
                print(err)
            else:
                print(data)
                count += 1

    print(f">> {count}/{REQ_NUM} requests recevied before disconnection")

    # re-try to check if the service is still alive
    resp = httpx.post(URL, json={"time": 0})
    if resp.status_code != HTTPStatus.OK:
        print(resp)
        raise RuntimeError()


if __name__ == "__main__":
    service = subprocess.Popen(shlex.split(f"python -u examples/echo.py --debug"))
    time.sleep(3)
    main()
    service.terminate()
    time.sleep(2)
