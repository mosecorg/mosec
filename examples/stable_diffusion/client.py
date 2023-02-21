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

import argparse

import httpx
import msgpack  # type: ignore

parser = argparse.ArgumentParser(
    prog="stable diffusion client demo",
)
parser.add_argument(
    "-p", "--prompt", default="a photo of an astronaut riding a horse on mars"
)
parser.add_argument(
    "-o", "--output", default="stable_diffusion_result.jpg", help="output filename"
)
parser.add_argument(
    "--port",
    default=8000,
    type=int,
    help="service port",
)


args = parser.parse_args()
resp = httpx.post(
    f"http://localhost:{args.port}/inference",
    data=msgpack.packb(args.prompt),
    timeout=httpx.Timeout(20),
)
if resp.status_code == 200:
    data = msgpack.unpackb(resp.content)
    with open(args.output, "wb") as f:
        f.write(data)
else:
    print(f"ERROR: <{resp.status_code}> {resp.text}")
