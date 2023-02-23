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
"""Example: Custom Environment setup"""

import os

from mosec import Server, Worker, get_logger

logger = get_logger()


class Inference(Worker):
    """Customisable inference class."""

    def __init__(self):
        super().__init__()
        # initialize your models here and allocate dedicated device to it
        device = os.environ["CUDA_VISIBLE_DEVICES"]
        logger.info("initializing model on device=%s", device)

    def forward(self, _: dict) -> dict:
        device = os.environ["CUDA_VISIBLE_DEVICES"]
        # NOTE self.worker_id is 1-indexed
        logger.info("worker=%d on device=%s is processing...", self.worker_id, device)
        return {"device": device}


if __name__ == "__main__":
    NUM_DEVICE = 4

    def _get_cuda_device(cid: int) -> dict:
        return {"CUDA_VISIBLE_DEVICES": str(cid)}

    server = Server()

    server.append_worker(
        Inference, num=NUM_DEVICE, env=[_get_cuda_device(x) for x in range(NUM_DEVICE)]
    )
    server.run()
