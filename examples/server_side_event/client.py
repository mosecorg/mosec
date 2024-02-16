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

import httpx
from httpx_sse import connect_sse

with httpx.Client() as client, connect_sse(
    client, "POST", "http://127.0.0.1:8000/inference", json={"text": "mosec"}
) as event_source:
    for sse in event_source.iter_sse():
        print(f"Event({sse.event}): {sse.data}")

# error handling
with httpx.Client() as client, connect_sse(
    client, "POST", "http://127.0.0.1:8000/inference", json={"error": "mosec"}
) as event_source:
    for sse in event_source.iter_sse():
        print(f"Event({sse.event}): {sse.data}")
