# Copyright 2024 MOSEC Authors
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

from __future__ import annotations

from os import environ

from msgspec import Struct
from sentence_transformers import CrossEncoder

from mosec import Server, Worker
from mosec.mixin import TypedMsgPackMixin

DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
WORKER_NUM = int(environ.get("WORKER_NUM", 1))


class Request(Struct, kw_only=True):
    query: str
    docs: list[str]


class Response(Struct, kw_only=True):
    scores: list[float]


class Encoder(TypedMsgPackMixin, Worker):
    def __init__(self):
        self.model_name = environ.get("MODEL_NAME", DEFAULT_MODEL)
        self.model = CrossEncoder(self.model_name)

    def forward(self, data: Request) -> Response:
        scores = self.model.predict([[data.query, doc] for doc in data.docs])
        return Response(scores=scores.tolist())


if __name__ == "__main__":
    server = Server()
    server.append_worker(Encoder, num=WORKER_NUM)
    server.run()
