# Copyright 2026 MOSEC Authors
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

from argparse import Namespace

import pytest

from mosec import Server, Worker
from mosec.mixin import TypedMsgPackMixin
from mosec.openapi import OPENAPI_METADATA_FILE, OPENAPI_SWAGGER_FILE


@pytest.mark.parametrize("dry_run", [False, True])
@pytest.mark.parametrize("boundary", ["data", "return"])
def test_invalid_typed_schema_fails_before_startup(dry_run, boundary, mocker, tmp_path):
    class InvalidWorker(TypedMsgPackMixin):
        def forward(self, data: int) -> int:
            return data

    InvalidWorker.forward.__annotations__[boundary] = "MissingModel"
    work_path = tmp_path / "runtime"
    mocker.patch(
        "mosec.server.parse_arguments",
        return_value=Namespace(
            path=str(work_path), timeout=3000, wait=10, dry_run=dry_run
        ),
    )
    server = Server()
    server.append_worker(InvalidWorker)
    start = mocker.patch.object(server, "_start_rs_runtime")
    signals = mocker.patch.object(server, "_handle_signal")
    dry_runner = mocker.patch("mosec.server.DryRunner")

    with pytest.raises(NameError, match="MissingModel"):
        server.run()

    start.assert_not_called()
    signals.assert_not_called()
    dry_runner.assert_not_called()
    assert not work_path.exists()


@pytest.mark.parametrize("dry_run", [False, True])
def test_schema_is_generated_once_before_runtime_start(dry_run, mocker, tmp_path):
    class ValidWorker(Worker):
        def forward(self, data: int) -> int:
            return data

    work_path = tmp_path / "runtime"
    mocker.patch(
        "mosec.server.parse_arguments",
        return_value=Namespace(
            path=str(work_path), timeout=3000, wait=10, dry_run=dry_run
        ),
    )
    server = Server()
    server.append_worker(ValidWorker)
    from mosec import server as server_module

    generate = mocker.spy(server_module, "generate_openapi")
    start = mocker.patch.object(server._rs_runtime_manager, "start")
    mocker.patch.object(server, "register_daemon")
    mocker.patch.object(server, "_handle_signal")
    mocker.patch.object(server, "_manage_py_runtime")
    mocker.patch.object(server, "_halt")
    dry_runner = mocker.patch("mosec.server.DryRunner")

    server.run()

    generate.assert_called_once_with(server._router)
    assert server._openapi_spec["openapi"] == "3.2.0"
    if dry_run:
        dry_runner.return_value.run.assert_called_once_with()
        start.assert_not_called()
        assert not work_path.exists()
    else:
        start.assert_called_once()
        assert (work_path / "config.json").is_file()
        assert (work_path / OPENAPI_METADATA_FILE).is_file()


@pytest.mark.parametrize("failure", ["asset-write", "rust-start"])
def test_startup_failures_cleanup_and_propagate(failure, mocker, tmp_path):
    class ValidWorker(Worker):
        def forward(self, data: int) -> int:
            return data

    work_path = tmp_path / "runtime"
    mocker.patch(
        "mosec.server.parse_arguments",
        return_value=Namespace(
            path=str(work_path),
            timeout=3000,
            wait=10,
            dry_run=False,
        ),
    )
    server = Server()
    server.append_worker(ValidWorker)
    mocker.patch.object(server, "_handle_signal")
    workers = mocker.patch.object(server, "_manage_py_runtime")
    start = mocker.patch.object(server._rs_runtime_manager, "start")
    halt = mocker.spy(server, "_halt")
    if failure == "asset-write":
        mocker.patch(
            "mosec.server.write_openapi_assets",
            side_effect=OSError("asset write failed"),
        )
    else:

        def fail_start(config_path):
            assert (config_path.parent / OPENAPI_METADATA_FILE).is_file()
            assert (config_path.parent / OPENAPI_SWAGGER_FILE).is_file()
            raise OSError("Rust start failed")

        start.side_effect = fail_start

    with pytest.raises(OSError, match="failed"):
        server.run()
    halt.assert_called_once_with()
    workers.assert_not_called()
    assert not work_path.exists()
    assert server._shutdown.is_set()
    assert server._shutdown_notify.is_set()
    if failure == "asset-write":
        start.assert_not_called()
    else:
        start.assert_called_once()
