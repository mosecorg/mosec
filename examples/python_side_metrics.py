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
"""Example: Adding metrics service."""

import os
import pathlib
import tempfile
from typing import List

from prometheus_client import (  # type: ignore
    CollectorRegistry,
    Counter,
    multiprocess,
    start_http_server,
)

from mosec import Server, ValidationError, Worker, get_logger

logger = get_logger()


# check the PROMETHEUS_MULTIPROC_DIR environment variable before import Prometheus
if not os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
    metric_dir_path = os.path.join(tempfile.gettempdir(), "prometheus_multiproc_dir")
    pathlib.Path(metric_dir_path).mkdir(parents=True, exist_ok=True)
    os.environ["PROMETHEUS_MULTIPROC_DIR"] = metric_dir_path


metric_registry = CollectorRegistry()
multiprocess.MultiProcessCollector(metric_registry)
counter = Counter("inference_result", "statistic of result", ("status", "worker_id"))


class Inference(Worker):
    """Sample Inference Worker."""

    def __init__(self):
        super().__init__()
        self.worker_id = str(self.worker_id)

    def deserialize(self, data: bytes) -> int:
        json_data = super().deserialize(data)
        try:
            res = int(json_data.get("num"))
        except Exception as err:
            raise ValidationError(err) from err
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
    start_http_server(5000)

    # Run the inference server
    server = Server()
    server.append_worker(Inference, num=2, max_batch_size=8)
    server.run()
