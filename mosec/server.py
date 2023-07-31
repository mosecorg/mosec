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

"""MOSEC server interface.

This module provides a way to define the service components for machine learning
model serving.

Dynamic Batching
----------------

    The user may enable the dynamic batching feature for any stage when the
    corresponding worker is appended, by setting the
    :py:meth:`append_worker(max_batch_size) <Server.append_worker>`.

Multiprocessing
---------------

    The user may spawn multiple processes for any stage when the
    corresponding worker is appended, by setting the
    :py:meth:`append_worker(num) <Server.append_worker>`.
"""

import json
import multiprocessing as mp
import pathlib
import shutil
import signal
import subprocess
import traceback
from collections import defaultdict
from multiprocessing.synchronize import Event
from time import sleep
from typing import Dict, List, Type, Union

from mosec.args import parse_arguments
from mosec.dry_run import DryRunner
from mosec.log import get_internal_logger
from mosec.runtime import PyRuntimeManager, RsRuntimeManager, Runtime
from mosec.utils import ParseTarget
from mosec.worker import MOSEC_REF_TEMPLATE, SSEWorker, Worker

logger = get_internal_logger()


GUARD_CHECK_INTERVAL = 1
MOSEC_RESERVED_ENDPOINTS = {"/", "/metrics", "/openapi"}


class Server:
    """MOSEC server interface.

    It allows users to sequentially append workers they implemented, builds
    the workflow pipeline automatically and starts up the server.
    """

    # pylint: disable=too-many-instance-attributes
    def __init__(self):
        """Initialize a MOSEC Server."""
        self._shutdown: Event = mp.get_context("spawn").Event()
        self._shutdown_notify: Event = mp.get_context("spawn").Event()
        self._configs: dict = vars(parse_arguments())

        self._py_runtime_manager: PyRuntimeManager = PyRuntimeManager(
            self._configs["path"], self._shutdown, self._shutdown_notify
        )
        self._rs_runtime_manager = RsRuntimeManager(self._configs["timeout"])
        self._router: Dict[str, List[Runtime]] = defaultdict(list)

        self._daemon: Dict[str, Union[subprocess.Popen, mp.Process]] = {}

        self._server_shutdown: bool = False

    def _handle_signal(self):
        signal.signal(signal.SIGTERM, self._terminate)
        signal.signal(signal.SIGINT, self._terminate)

    def _validate_server(self):
        assert self._py_runtime_manager.worker_count > 0, (
            "no worker registered\n"
            "help: use `.append_worker(...)` to register at least one worker"
        )

    def _check_daemon(self):
        for name, proc in self._daemon.items():
            if proc is None:
                continue
            code = None
            if isinstance(proc, mp.Process):
                code = proc.exitcode
            elif isinstance(proc, subprocess.Popen):
                code = proc.poll()

            if code is not None:
                self._terminate(
                    code,
                    f"mosec daemon [{name}] exited on error code: {code}",
                )

    def _start_rs_runtime(self):
        """Subprocess to start the rust runtime manager program."""
        if self._server_shutdown:
            return

        # dump the config to a JSON file
        config_path = pathlib.Path(self._configs["path"]) / "config.json"
        configs = {"runtimes": [], "routes": []}
        for key, value in self._configs.items():
            if key in ("dry_run", "debug", "wait"):
                continue
            configs[key] = value
        for runtime in self._py_runtime_manager.runtimes:
            configs["runtimes"].append(
                {
                    "worker": runtime.name,
                    "max_batch_size": runtime.max_batch_size,
                    "max_wait_time": runtime.max_wait_time,
                }
            )
        for endpoint, pipeline in self._router.items():
            configs["routes"].append(
                {
                    "endpoint": endpoint,
                    "workers": [runtime.name for runtime in pipeline],
                    "is_sse": issubclass(pipeline[-1].worker, SSEWorker),
                    **generate_openapi([runtime.worker for runtime in pipeline]),
                }
            )
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as file:
            json.dump(configs, file, indent=2)

        process = self._rs_runtime_manager.start(config_path)
        self.register_daemon("rs_runtime", process)

    def _terminate(self, signum, framestack):
        logger.info("received signum[%s], terminating server [%s]", signum, framestack)
        self._server_shutdown = True

    def _manage_py_runtime(self):
        init = True
        while not self._server_shutdown:
            failed_runtime = self._py_runtime_manager.check_and_start(init)
            if failed_runtime is not None:
                self._terminate(
                    1,
                    f"all the {failed_runtime.name} workers exited;"
                    " please check for bugs or socket connection issues",
                )
            init = False
            self._check_daemon()
            sleep(GUARD_CHECK_INTERVAL)

    def _halt(self):
        """Graceful shutdown."""
        # notify the rs runtime to shutdown
        self._shutdown_notify.set()
        self._rs_runtime_manager.halt()
        # shutdown py runtime manager
        self._shutdown.set()
        shutil.rmtree(self._configs["path"], ignore_errors=True)
        logger.info("mosec exited normally")

    def register_daemon(self, name: str, proc: subprocess.Popen):
        """Register a daemon to be monitored.

        Args:
            name: the name of this daemon
            proc: the process handle of the daemon
        """
        assert isinstance(name, str), "daemon name should be a string"
        assert isinstance(
            proc, (mp.Process, subprocess.Popen)
        ), f"{type(proc)} is not a process or subprocess"
        self._daemon[name] = proc

    # pylint: disable=too-many-arguments
    def append_worker(
        self,
        worker: Type[Worker],
        num: int = 1,
        max_batch_size: int = 1,
        max_wait_time: int = 0,
        start_method: str = "spawn",
        env: Union[None, List[Dict[str, str]]] = None,
        timeout: int = 0,
        route: Union[str, List[str]] = "/inference",
    ):
        """Sequentially appends workers to the workflow pipeline.

        Args:
            worker: the class you inherit from :class:`Worker<mosec.worker.Worker>`
                which implements the :py:meth:`forward<mosec.worker.Worker.forward>`
            num: the number of processes for parallel computing (>=1)
            max_batch_size: the maximum batch size allowed (>=1), will enable the
                dynamic batching if it > 1
            max_wait_time: the maximum wait time (millisecond) for dynamic batching,
                needs to be used with `max_batch_size` to enable the feature. If not
                configure, will use the CLI argument `--wait` (default=10ms)
            start_method: the process starting method ("spawn" or "fork"). (DO NOT
                change this unless you understand the difference between them)
            env: the environment variables to set before starting the process
            timeout: the timeout (second) for each worker forward processing (>=1)
            route: the route path for this worker. If not configured, will use the
                default route path `/inference`. If a list is provided, different
                route paths will share the same worker.
        """
        timeout = timeout if timeout >= 1 else self._configs["timeout"] // 1000
        max_wait_time = max_wait_time if max_wait_time >= 1 else self._configs["wait"]
        runtime = Runtime(
            worker,
            num,
            max_batch_size,
            max_wait_time,
            timeout,
            start_method,
            env,
        )
        self._register_route(runtime, route)
        self._py_runtime_manager.append(runtime)

    def register_runtime(self, routes: Dict[str, List[Runtime]]):
        """Register the runtime to the routes."""
        if self._py_runtime_manager.worker_count > 0:
            raise RuntimeError(
                "`register_runtime` can only be registered to an empty mosec server"
            )
        unique_runtimes = set()
        for endpoint, runtimes in routes.items():
            for runtime in runtimes:
                self._register_route(runtime, endpoint)
                unique_runtimes.add(runtime)
        for runtime in unique_runtimes:
            self._py_runtime_manager.append(runtime)

    def _register_route(self, runtime: Runtime, route: Union[str, List[str]]):
        """Register the route path for the worker."""
        if isinstance(route, str):
            if route in MOSEC_RESERVED_ENDPOINTS:
                raise ValueError(f"'{route}' is reserved, try another one")
            self._router[route].append(runtime)
        elif isinstance(route, list):
            for endpoint in route:
                if endpoint in MOSEC_RESERVED_ENDPOINTS:
                    raise ValueError(f"'{endpoint}' is reserved, try another one")
                self._router[endpoint].append(runtime)

    def run(self):
        """Start the mosec model server."""
        self._validate_server()
        if self._configs["dry_run"]:
            DryRunner(self._router).run()
            return

        self._handle_signal()
        self._start_rs_runtime()
        try:
            self._manage_py_runtime()
        # pylint: disable=broad-except
        except Exception:
            logger.error(traceback.format_exc().replace("\n", " "))
        self._halt()


def generate_openapi(workers: List[Type[Worker]]):
    """Generate the OpenAPI specification for one pipeline."""
    if not workers:
        return {}
    request_worker_cls, response_worker_cls = workers[0], workers[-1]
    input_schema, input_components = request_worker_cls.get_forward_json_schema(
        ParseTarget.INPUT, MOSEC_REF_TEMPLATE
    )
    return_schema, return_components = response_worker_cls.get_forward_json_schema(
        ParseTarget.RETURN, MOSEC_REF_TEMPLATE
    )

    def make_body(description, mime, schema):
        if not schema:
            return None
        return {"description": description, "content": {mime: {"schema": schema}}}

    return {
        "request_body": make_body(
            "Mosec Inference Request Body",
            request_worker_cls.resp_mime_type,
            input_schema,
        ),
        "responses": None
        if not return_schema
        else {
            "200": make_body(
                "Mosec Inference Result",
                response_worker_cls.resp_mime_type,
                return_schema,
            )
        },
        "schemas": {**input_components, **return_components},
        "mime": response_worker_cls.resp_mime_type,
    }
