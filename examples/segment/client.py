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

import gzip
from http import HTTPStatus
from io import BytesIO

import httpx
import msgpack  # type: ignore
import numbin
import numpy as np
from PIL import Image  # type: ignore

truck_image = Image.open(
    BytesIO(
        httpx.get(
            "https://raw.githubusercontent.com/facebookresearch/sam2/main/notebooks/images/truck.jpg"
        ).content
    )
)
array = np.array(truck_image.convert("RGB"))
# assume we have obtains the low resolution mask from the previous step
mask = np.zeros((256, 256))

resp = httpx.post(
    "http://127.0.0.1:8000/inference",
    content=gzip.compress(
        msgpack.packb(  # type: ignore
            {
                "image": numbin.dumps(array),
                "mask": numbin.dumps(mask),
                "labels": [1, 1],
                "point_coords": [[500, 375], [1125, 625]],
            }
        )
    ),
    headers={"Accept-Encoding": "gzip", "Content-Encoding": "gzip"},
)
assert resp.status_code == HTTPStatus.OK, resp.status_code
res = numbin.loads(msgpack.loads(resp.content))
assert res.shape == array.shape[:2], f"expect {array.shape[:2]}, got {res.shape}"
