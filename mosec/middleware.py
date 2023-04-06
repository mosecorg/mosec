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

"""MOSEC middleware interface.

This module provides the interface to define a middleware with such behaviors:

    1. initialize
    2. preprocess data to forward function or another middleware
    3. postprocess data from forward function or another middleware
"""

from functools import partial
from typing import Any, List, Type, Union

from mosec.ipc import IPCWrapper

STAGE_INGRESS = "ingress"
STAGE_EGRESS = "egress"


class Middleware:
    """Middleware interface.

    It provides pre and post processing methods for data.
    """

    _worker_id: int = 0
    _stage: str = ""

    def __init__(self) -> None:
        """Initialize the middleware.

        This method can be overridden and parameters can be passed
        using `functools.partial`.
        """

    @property
    def stage(self) -> str:
        """Return the stage name."""
        return self._stage

    @stage.setter
    def stage(self, stage):
        self._stage = stage

    @property
    def worker_id(self) -> int:
        """Return the ID of this worker instance.

        This property returns the worker ID in the range of [1, ... , ``num``]
        (``num`` as configured in
        :py:meth:`append_worker(num) <mosec.server.Server.append_worker>`)
        to differentiate workers in the same stage.
        """
        return self._worker_id

    @worker_id.setter
    def worker_id(self, worker_id):
        self._worker_id = worker_id

    # pylint: disable=no-self-use
    def preprocess(self, data: List[Any]) -> List[Any]:
        """Process data before passing it to the next middleware or `forward`.

        Override this method in child classes to implement custom pre-processing logic.

        Arguments:
            data: the input data

        Returns:
            the processed data
        """
        return data

    # pylint: disable=no-self-use
    def postprocess(self, data: List[Any]) -> List[Any]:
        """Process data after receiving it from the previous middleware or `forward`.

        Override this method in child classes to implement custom post-processing logic.

        Arguments:
            data: the output data

        Returns:
            the processed data
        """
        return data


class MiddlewareChain:
    """A chain of middlewares.

    It provides pre and post processing methods for data
        using the middlewares in the chain.
    """

    def __init__(
        self,
        middlewares: List[Union[Type[Middleware], partial]],
        worker_id: int,
        stage: str,
    ) -> None:
        """Initialize the middleware chain.

        Arguments:
            middlewares (list): a list of middleware classes or callable objects.
            worker_id (int): identification number for worker processes at the same
                stage.
            stage (str): identifier to distinguish the first and last stages.
        """
        self.middlewares = [constructor() for constructor in middlewares]
        for middleware in self.middlewares:
            middleware.worker_id = worker_id
            middleware.stage = stage

    def preprocess(self, data: Any) -> Any:
        """Process data before passing it to the forward function.

        This method applies each middleware's pre method to the data
            in the order they appear in the chain.

        Arguments:
            data: the input data

        Returns:
            the processed data
        """
        for middleware in self.middlewares:
            data = middleware.preprocess(data)
        return data

    def postprocess(self, data: Any) -> Any:
        """Process data after receiving it from the forward function.

        This method applies each middleware's post method to the data
            in the reverse order they appear in the chain.

        Arguments:
            data: the output data

        Returns:
            the processed data
        """
        for middleware in reversed(self.middlewares):
            data = middleware.postprocess(data)
        return data


class IPCMiddleware(Middleware, IPCWrapper):
    """Middleware for inter-process communication.

    This middleware is used for inter-process communication, and it provides methods
    for pre and post processing data, as well as a put and get method for sending
    and receiving data across different processes.

    For users who want to implement their own IPCMiddleware, it is recommended to
    implement the `get` and `put` method,
    override the `_preprocess` and `_postprocess` methods.
    """

    def _preprocess(self, ids: List[Any]) -> List[Any]:
        """Process data before passing it to the next middleware or `forward`.

        Arguments:
            ids: the ID(s) of the data to be received.

        Returns:
            the processed data after it has been received.
        """
        return self.get(ids)

    def preprocess(self, data: List[Any]) -> List[Any]:
        """Process data before passing it to the next middleware or `forward`.

        Usually, this method just forward the data in `ingress` stage,
        and get data from another process in other stages.
        User are out recommended to overwrite this method.

        Arguments:
            data: the input data

        Returns:
            the processed data, or the unprocessed data if the stage is STAGE_INGRESS.
        """
        if self.stage == STAGE_INGRESS:
            return data
        return self._preprocess(data)

    def _postprocess(self, data: List[Any]) -> List[Any]:
        """Process data before receiving it from the previous middleware or `forward`.

        Arguments:
            data: the output data

        Returns:
            the processed data (ids) after it has been put into another process.
        """
        return self.put(data)

    def postprocess(self, data: List[Any]) -> List[Any]:
        """Process data before receiving it from the previous middleware or `forward`.

        Usually, this method just forward the data in `egress` stage,
        and put data into another process in other stages.
        User are out recommended to overwrite this method.

        Arguments:
            data: the output data

        Returns:
            the processed data, or the unprocessed data if the stage is STAGE_EGRESS.
        """
        if self.stage == STAGE_EGRESS:
            return data
        return self._postprocess(data)
