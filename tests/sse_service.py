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

from mosec import Server, ValidationError, Worker, get_logger

logger = get_logger()


class Preprocess(Worker):
    def forward(self, data):
        text = data.get("text")
        if text is None:
            raise ValidationError("text is required")
        return text


class Inference(Worker):
    def forward(self, data):
        epoch = 5
        for _ in range(epoch):
            for j in range(len(data)):
                self.send_stream_event(f"{data[j]}", index=j)

        # this return value will be ignored
        return data


if __name__ == "__main__":
    server = Server()
    server.append_worker(Preprocess)
    server.append_worker(Inference, max_batch_size=2)
    server.run()
