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
"""Example: Sample Resnet server."""

import base64
import logging
from typing import List
from urllib.request import urlretrieve

import cv2  # type: ignore
import numpy as np  # type: ignore
import torch  # type: ignore
import torchvision  # type: ignore

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

INFERENCE_BATCH_SIZE = 16


class Preprocess(Worker):
    """Sample Preprocess worker"""

    def forward(self, data: dict) -> np.ndarray:
        # Customized validation for input key and field content; raise
        # ValidationError so that the client can get 422 as http status
        try:
            image = data["image"]
            img = np.frombuffer(base64.b64decode(image), np.uint8)
            img = cv2.imdecode(img, cv2.IMREAD_COLOR)[:, :, ::-1]  # bgr -> rgb
        except KeyError as err:
            raise ValidationError(f"cannot find key {err}") from err
        except Exception as err:
            raise ValidationError(f"cannot decode as image data: {err}") from err

        img = cv2.resize(img, (256, 256))
        crop_img = (
            img[16 : 16 + 224, 16 : 16 + 224].astype(np.float32) / 255
        )  # center crop
        crop_img -= [0.485, 0.456, 0.406]
        crop_img /= [0.229, 0.224, 0.225]
        crop_img = np.transpose(crop_img, (2, 0, 1))
        return crop_img


class Inference(Worker):
    """Sample Inference worker"""

    def __init__(self):
        super().__init__()
        self.device = (
            torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")
        )
        logger.info("using computing device: %s", self.device)
        self.model = torchvision.models.resnet50(pretrained=True)
        self.model.eval()
        self.model.to(self.device)

        # Overwrite self.example for warmup
        self.example = [
            np.zeros((3, 244, 244), dtype=np.float32)
        ] * INFERENCE_BATCH_SIZE

    def forward(self, data: List[np.ndarray]) -> List[int]:
        logger.info("processing batch with size: %d", len(data))
        with torch.no_grad():
            batch = torch.stack([torch.tensor(arr, device=self.device) for arr in data])
            output = self.model(batch)
            top1 = torch.argmax(output, dim=1)
        return top1.cpu().tolist()


class Postprocess(Worker):
    """Sample Postprocess worker"""

    def __init__(self):
        super().__init__()
        logger.info("loading categories file...")
        local_filename, _ = urlretrieve(
            "https://raw.githubusercontent.com/pytorch/hub/master/imagenet_classes.txt"
        )

        with open(local_filename, encoding="utf8") as file:
            self.categories = list(map(lambda x: x.strip(), file.readlines()))

    def forward(self, data: int) -> dict:
        return {"category": self.categories[data]}


if __name__ == "__main__":
    server = Server()
    server.append_worker(Preprocess, num=4)
    server.append_worker(Inference, num=2, max_batch_size=INFERENCE_BATCH_SIZE)
    server.append_worker(Postprocess, num=1)
    server.run()
