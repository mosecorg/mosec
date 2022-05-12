# Copyright 2022 MOSEC
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
import pathlib
import tempfile
import threading
from typing import List
from wsgiref.simple_server import make_server

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


# check the PROMETHEUS_MULTIPROC_DIR environment variable before import Prometheus
if not os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
    metric_dir_path = os.path.join(tempfile.gettempdir(), "prometheus_multiproc_dir")
    pathlib.Path(metric_dir_path).mkdir(parents=True, exist_ok=True)
    os.environ["PROMETHEUS_MULTIPROC_DIR"] = metric_dir_path

from prometheus_client import (  # type: ignore  # noqa: E402
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    generate_latest,
    multiprocess,
)

metric_registry = CollectorRegistry()
multiprocess.MultiProcessCollector(metric_registry)
counter = Counter("inference_result", "statistic of result", ("status", "worker_id"))


def metric_app(environ, start_response):
    data = generate_latest(metric_registry)
    start_response(
        "200 OK",
        [("Content-Type", CONTENT_TYPE_LATEST), ("Content-Length", str(len(data)))],
    )
    return iter([data])


def metric_service(host="", port=8080):
    with make_server(host, port, metric_app) as httpd:
        httpd.serve_forever()


class Inference(Worker):
    def __init__(self):
        super().__init__()
        self.worker_id = str(self.id)

    def deserialize(self, data: bytes) -> int:
        json_data = super().deserialize(data)
        try:
            res = int(json_data.get("num"))
        except Exception as err:
            raise ValidationError(err)
        return res

    def forward(self, data: List[int]) -> List[bool]:
        avg = sum(data) / len(data)
        ans = [x >= avg for x in data]
        counter.labels(status="true", worker_id=self.worker_id).inc(sum(ans))
        counter.labels(status="false", worker_id=self.worker_id).inc(
            len(ans) - sum(ans)
        )
        return ans


if __name__ == "__main__":
    # Run the metrics server in another thread.
    metric_thread = threading.Thread(target=metric_service, daemon=True)
    metric_thread.start()

    # Run the inference server
    server = Server()
    server.append_worker(Inference, num=2, max_batch_size=8)
    server.run()
