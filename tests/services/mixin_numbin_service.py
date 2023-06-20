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

from typing import Dict, List

import numpy as np

from mosec import Server, Worker
from mosec.mixin import NumBinIPCMixin


class Preprocess(NumBinIPCMixin, Worker):
    def forward(self, data: Dict[str, str]) -> np.ndarray:
        num = int(data.get("num", 10))
        arr = np.ones(num) * (1 / num)
        return arr


class Inference(NumBinIPCMixin, Worker):
    def forward(self, data: List[np.ndarray]) -> List[str]:
        res = ["equal" if np.equal(1, arr.sum()) else "unequal" for arr in data]
        return res


if __name__ == "__main__":
    server = Server()
    server.append_worker(Preprocess)
    server.append_worker(Inference, max_batch_size=8)
    server.run()
