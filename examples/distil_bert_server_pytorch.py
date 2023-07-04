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
"""Example: Mosec with Pytorch Distil BERT."""

from typing import Any, List

import torch  # type: ignore
from transformers import (  # type: ignore
    AutoModelForSequenceClassification,
    AutoTokenizer,
)

from mosec import Server, Worker, get_logger

logger = get_logger()

# type alias
Returns = Any

INFERENCE_BATCH_SIZE = 32
INFERENCE_WORKER_NUM = 1


class Preprocess(Worker):
    """Preprocess BERT on current setup."""

    def __init__(self):
        super().__init__()
        self.tokenizer = AutoTokenizer.from_pretrained(
            "distilbert-base-uncased-finetuned-sst-2-english"
        )

    def deserialize(self, data: bytes) -> str:
        # Override `deserialize` for the *first* stage;
        # `data` is the raw bytes from the request body
        return data.decode()

    def forward(self, data: str) -> Returns:
        tokens = self.tokenizer.encode(data, add_special_tokens=True)
        return tokens


class Inference(Worker):
    """Pytorch Inference class"""

    resp_mime_type = "text/plain"

    def __init__(self):
        super().__init__()
        self.device = (
            torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")
        )
        logger.info("using computing device: %s", self.device)
        self.model = AutoModelForSequenceClassification.from_pretrained(
            "distilbert-base-uncased-finetuned-sst-2-english"
        )
        self.model.eval()
        self.model.to(self.device)

        # Overwrite self.example for warmup
        self.example = [
            [101, 2023, 2003, 1037, 8403, 4937, 999, 102] * 5  # make sentence longer
        ] * INFERENCE_BATCH_SIZE

    def forward(self, data: List[Returns]) -> List[str]:
        tensors = [torch.tensor(token) for token in data]
        with torch.no_grad():
            result = self.model(
                torch.nn.utils.rnn.pad_sequence(tensors, batch_first=True).to(
                    self.device
                )
            )[0]
        scores = result.softmax(dim=1).cpu().tolist()
        return [f"positive={p}" for (_, p) in scores]

    def serialize(self, data: str) -> bytes:
        # Override `serialize` for the *last* stage;
        # `data` is the string from the `forward` output
        return data.encode()


if __name__ == "__main__":
    server = Server()
    server.append_worker(Preprocess, num=2 * INFERENCE_WORKER_NUM)
    server.append_worker(
        Inference, max_batch_size=INFERENCE_BATCH_SIZE, num=INFERENCE_WORKER_NUM
    )
    server.run()
