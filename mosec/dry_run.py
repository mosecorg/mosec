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

"""Dry run the service."""

from __future__ import annotations

import json
import time
from multiprocessing.context import SpawnContext, SpawnProcess
from typing import TYPE_CHECKING, Dict, List

from .env import env_var_context
from .log import get_logger
from .worker import Worker

if TYPE_CHECKING:
    from multiprocessing.connection import PipeConnection  # type: ignore

logger = get_logger()


def dry_run_func(
    worker_cls: type[Worker],
    batch: int,
    receiver: PipeConnection,
    sender: PipeConnection,
    ingress: bool,
):
    """Dry run simulation function."""
    worker = worker_cls()
    data = receiver.recv() if ingress else worker.deserialize(receiver.recv_bytes())
    logger.info("%s received %s", worker, data)
    if batch > 1:
        data = worker.forward([data])[0]
    else:
        data = worker.forward(data)
    logger.info("%s inference result: %s", worker, data)
    data = worker.serialize(data)
    sender.send_bytes(data)


class DryRunner:
    """Dry run the full stage.

    If examples are provided in the ingress :py:class:`Worker <mosec.worker.Worker>`,
    they will be used to pass through all the stages.

    For each stage, there will be only 1 worker. If `env` is provided during
    :py:meth:`append_worker <mosec.server.Server.append_worker>`, the 1st one
    will be used.
    """

    def __init__(
        self,
        workers: List[type[Worker]],
        batches: List[int],
        envs: List[None | List[Dict[str, str]]],
    ):
        """Init dry runner."""
        logger.info("init dry runner for %s", workers)
        self.process_context = SpawnContext()
        self.workers = workers
        self.batches = batches
        self.envs = envs
        self.pool: List[SpawnProcess] = []
        self.sender_pipes: List[PipeConnection] = []
        self.receiver_pipes: List[PipeConnection] = []

    def new_pipe(self):
        """Create new pipe for dry run workers to communicate."""
        receiver, sender = self.process_context.Pipe(duplex=False)
        self.sender_pipes.append(sender)
        self.receiver_pipes.append(receiver)

    def run(self):
        """Execute thr dry run process."""
        self.new_pipe()
        for i, (worker, batch, env) in enumerate(
            zip(self.workers, self.batches, self.envs)
        ):
            self.new_pipe()
            coordinator = self.process_context.Process(
                target=dry_run_func,
                args=(
                    worker,
                    batch,
                    self.receiver_pipes[-2],
                    self.sender_pipes[-1],
                    i == 0,
                ),
                daemon=True,
            )

            with env_var_context(env, 0):
                coordinator.start()

            self.pool.append(coordinator)

        logger.info("dry run init successful")
        self.warmup()
        logger.info("dry run exit")

    def warmup(self):
        """Warmup the service.

        Only one example will be used.
        """
        ingress = self.workers[0]
        example = None
        if ingress.example:
            assert isinstance(
                ingress.example, list
            ), "`example` should be a list of data"
            example = ingress.example[0]
        elif ingress.multi_examples:
            assert isinstance(ingress.multi_examples, list) and isinstance(
                ingress.multi_examples[0], list
            ), "`multi_examples` should be a list of list data"
            example = ingress.multi_examples[0][0]

        if not example:
            logger.info("cannot find the example in the 1st stage worker, skip warmup")
            return

        sender, receiver = self.sender_pipes[0], self.receiver_pipes[-1]
        start_time = time.perf_counter()
        sender.send(example)
        res = receiver.recv_bytes()
        duration = time.perf_counter() - start_time
        logger.info(
            "dry run result: %s",
            json.dumps(
                {
                    "req": example,
                    "size": len(res),
                    "duration": duration,
                }
            ),
        )
