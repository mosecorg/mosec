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

# refer to https://github.com/facebookresearch/sam2/blob/main/notebooks/image_predictor_example.ipynb

import numbin
import torch  # type: ignore
from sam2.sam2_image_predictor import SAM2ImagePredictor  # type: ignore

from mosec import Server, Worker, get_logger
from mosec.mixin import MsgpackMixin

logger = get_logger()
MIN_TF32_MAJOR = 8


class SegmentAnything(MsgpackMixin, Worker):
    def __init__(self):
        # select the device for computation
        if torch.cuda.is_available():
            device = torch.device("cuda")
        elif torch.backends.mps.is_available():
            device = torch.device("mps")
        else:
            device = torch.device("cpu")
        logger.info("using device: %s", device)

        self.predictor = SAM2ImagePredictor.from_pretrained(
            "facebook/sam2-hiera-large", device=device
        )

        if device.type == "cuda":
            # use bfloat16
            torch.autocast("cuda", dtype=torch.bfloat16).__enter__()
            # turn on tf32 for Ampere GPUs (https://pytorch.org/docs/stable/notes/cuda.html#tensorfloat-32-tf32-on-ampere-devices)
            if torch.cuda.get_device_properties(0).major >= MIN_TF32_MAJOR:
                torch.backends.cuda.matmul.allow_tf32 = True
                torch.backends.cudnn.allow_tf32 = True

    def forward(self, data: dict) -> bytes:
        with torch.inference_mode():
            self.predictor.set_image(numbin.loads(data["image"]))
            masks, _, _ = self.predictor.predict(
                point_coords=data["point_coords"],
                point_labels=data["labels"],
                mask_input=numbin.loads(data["mask"])[None, :, :],
                multimask_output=False,
            )
        return numbin.dumps(masks[0])


if __name__ == "__main__":
    server = Server()
    server.append_worker(SegmentAnything, num=1, max_batch_size=1)
    server.run()
