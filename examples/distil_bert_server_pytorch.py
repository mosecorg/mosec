import logging
from typing import List, TypeVar

import torch  # type: ignore
from transformers import (  # type: ignore
    AutoModelForSequenceClassification,
    AutoTokenizer,
)

from mosec import Server, Worker

T = TypeVar("T")

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
    def __init__(self):
        super().__init__()
        self.tokenizer = AutoTokenizer.from_pretrained(
            "distilbert-base-uncased-finetuned-sst-2-english"
        )

    def deserialize(self, data: bytes) -> str:
        # Override `deserialize` for the *first* stage;
        # `data` is the raw bytes from the request body
        return data.decode()

    def forward(self, data: str) -> T:
        tokens = self.tokenizer.encode(data, add_special_tokens=True)
        return tokens


class Inference(Worker):
    def __init__(self):
        super().__init__()
        self.device = (
            torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")
        )
        logger.info(f"using computing device: {self.device}")
        self.model = AutoModelForSequenceClassification.from_pretrained(
            "distilbert-base-uncased-finetuned-sst-2-english"
        )
        self.model.eval()
        self.model.to(self.device)

        # overwrite self.example for warmup
        self.example = [
            [101, 2023, 2003, 1037, 8403, 4937, 999, 102] * 5  # make sentence longer
        ] * INFERENCE_BATCH_SIZE

    def forward(self, data: List[T]) -> List[str]:
        data = [torch.tensor(token) for token in data]
        with torch.no_grad():
            result = self.model(
                torch.nn.utils.rnn.pad_sequence(data, batch_first=True)
            )[0]
        scores = result.softmax(dim=1).cpu().tolist()
        return [f"positive={p}" for (_, p) in scores]

    def serialize(self, data: str) -> bytes:
        # Override `serialize` for the *last* stage;
        # `data` is the string from the `forward` output
        return data.encode()


if __name__ == "__main__":
    server = Server()
    server.append_worker(Preprocess, num=8)
    server.append_worker(Inference, max_batch_size=INFERENCE_BATCH_SIZE)
    server.run()
