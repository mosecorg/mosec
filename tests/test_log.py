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

"""Test multiprocessing logging configuration."""

import logging

from mosec.log import get_log_level, get_logger, set_logger
from tests.utils import env_context


def test_get_logger():
    with env_context():
        logger = get_logger()
        assert logger.level == logging.INFO

    with env_context(MOSEC_LOG_LEVEL="warning"):
        set_logger(get_log_level())
        logger = get_logger()
        assert logger.level == logging.WARNING

    # `--debug` has higher priority
    with env_context(MOSEC_DEBUG="true", MOSEC_LOG_LEVEL="warning"):
        set_logger(get_log_level())
        logger = get_logger()
        assert logger.level == logging.DEBUG
