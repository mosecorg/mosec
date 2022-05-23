# Copyright 2022 MOSEC Authors
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

import logging
import os

from mosec import Server, Worker
from mosec.errors import ValidationError

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    "%(asctime)s - %(process)d - %(levelname)s - %(filename)s:%(lineno)s - %(message)s"
)
sh = logging.StreamHandler()
sh.setFormatter(formatter)
logger.addHandler(sh)


class Inference(Worker):
    def __init__(self):
        # initialize your models here and allocate dedicated device to it
        device = os.environ["CUDA_VISIBLE_DEVICES"]
        logger.info(f"Initializing model on device={device}")

    def forward(self, _: dict) -> dict:
        device = os.environ["CUDA_VISIBLE_DEVICES"]
        # NOTE self.worker_id is 1-indexed
        logger.info(f"Worker={self.worker_id} on device={device} is processing...")
        return {"device": device}


if __name__ == "__main__":
    num_device = 4

    def _get_cuda_device(cid: int) -> dict:
        return {"CUDA_VISIBLE_DEVICES": str(cid)}

    server = Server()

    server.append_worker(
        Inference, num=num_device, env=[_get_cuda_device(x) for x in range(num_device)]
    )
    server.run()
