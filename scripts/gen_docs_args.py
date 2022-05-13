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

import subprocess

import mkdocs_gen_files  # type: ignore

process = subprocess.Popen(
    ["python", "mosec/args.py", "--help"], stdout=subprocess.PIPE
)
stdout = process.communicate()[0].decode()
stdout = stdout.replace("args.py", "python your_model_server.py")
mkstr = f"```text\n{stdout}\n```"

with mkdocs_gen_files.open("argument.md", "w") as f:
    print(mkstr, file=f)
