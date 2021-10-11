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
    def forward(self, req: dict) -> np.ndarray:
        # Customized validation for input key and field content; raise
        # ValidationError so that the client can get 422 as http status
        try:
            image = req["image"]
            im = np.frombuffer(base64.b64decode(image), np.uint8)
            im = cv2.imdecode(im, cv2.IMREAD_COLOR)[:, :, ::-1]  # bgr -> rgb
        except KeyError as err:
            raise ValidationError(f"cannot find key {err}")
        except Exception as err:
            raise ValidationError(f"cannot decode as image data: {err}")

        im = cv2.resize(im, (256, 256))
        crop_im = (
            im[16 : 16 + 224, 16 : 16 + 224].astype(np.float32) / 255
        )  # center crop
        crop_im -= [0.485, 0.456, 0.406]
        crop_im /= [0.229, 0.224, 0.225]
        crop_im = np.transpose(crop_im, (2, 0, 1))
        return crop_im


class Inference(Worker):
    def __init__(self):
        super().__init__()
        self.device = (
            torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")
        )
        logger.info(f"using computing device: {self.device}")
        self.model = torchvision.models.resnet50(pretrained=True)
        self.model.eval()
        self.model.to(self.device)

        # Overwrite self.example for warmup
        self.example = [
            np.zeros((3, 244, 244), dtype=np.float32)
        ] * INFERENCE_BATCH_SIZE

    def forward(self, data: List[np.ndarray]) -> List[int]:
        logger.info(f"processing batch with size: {len(data)}")
        with torch.no_grad():
            batch = torch.stack([torch.tensor(arr, device=self.device) for arr in data])
            output = self.model(batch)
            top1 = torch.argmax(output, dim=1)
        return top1.cpu().tolist()


class Postprocess(Worker):
    def __init__(self):
        super().__init__()
        logger.info("loading categories file...")
        local_filename, _ = urlretrieve(
            "https://raw.githubusercontent.com/pytorch/hub/master/imagenet_classes.txt"
        )

        with open(local_filename) as f:
            self.categories = list(map(lambda x: x.strip(), f.readlines()))

    def forward(self, data: int) -> dict:
        return {"category": self.categories[data]}


if __name__ == "__main__":
    server = Server()
    server.append_worker(Preprocess, num=4)
    server.append_worker(Inference, num=2, max_batch_size=INFERENCE_BATCH_SIZE)
    server.append_worker(Postprocess, num=1)
    server.run()
