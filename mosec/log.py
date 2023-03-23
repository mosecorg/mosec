# Copyright 2023 MOSEC Authors
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

"""MOSEC multiprocessing logging configurations."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, MutableMapping

from .args import mosec_args

MOSEC_LOG_NAME = __name__
USER_LOG_NAME = "MOSEC_USER_LOG"


class MosecFormat(logging.Formatter):
    """Basic mosec log formatter.

    This class uses `datetime` instead of `localtime` to get accurate milliseconds.
    """

    default_time_format = "%Y-%m-%dT%H:%M:%S.%f%z"

    def formatTime(self, record: logging.LogRecord, datefmt=None) -> str:
        """Convert to datetime with timezone."""
        time = datetime.fromtimestamp(record.created).astimezone()
        return datetime.strftime(time, datefmt if datefmt else self.default_time_format)


class DebugFormat(MosecFormat):
    """Colorful debug formatter."""

    Purple = "\x1b[35m"
    Blue = "\x1b[34m"
    Green = "\x1b[32m"
    Yellow = "\x1b[33m"
    Red = "\x1b[31m"
    Reset = "\x1b[0m"

    default_format = (
        "%(asctime)s %(levelname)s %(prefix)s::%(filename)s:%(lineno)s"
        " [%(process)d]: %(message)s"
    )

    def __init__(
        self, fmt: str | None = None, datefmt: str | None = None, prefix: str = ""
    ) -> None:
        """Init with `%` style format.

        Args:
            fmt (str): logging message format (% style)
            datefmt (str): datatime format
        """
        # partially align with rust tracing_subscriber
        self.colors = {
            logging.DEBUG: self.Blue,
            logging.INFO: self.Green,
            logging.WARNING: self.Yellow,
            logging.ERROR: self.Red,
            logging.CRITICAL: self.Purple,
        }
        super().__init__(fmt or self.default_format, datefmt, "%")
        self.prefix = prefix

    def format_level(self, name: str, level: int) -> str:
        """Format a level name with the corresponding color."""
        if level not in self.colors:
            return name
        return f"{self.colors[level]}{name}{self.Reset}"

    def formatMessage(self, record: logging.LogRecord) -> str:
        """Format the logging with colorful level names."""
        fmt = self.default_format.replace(
            "%(levelname)s",
            self.format_level(record.levelname, record.levelno),
        ).replace("%(prefix)s", self.prefix)
        return fmt % record.__dict__


class JSONFormat(MosecFormat):
    """JSON log formatter."""

    def __init__(
        self, fmt: str | None = None, datefmt: str | None = None, prefix: str = ""
    ) -> None:
        super().__init__(fmt, datefmt, "%")
        self.prefix = prefix

    def format(self, record: logging.LogRecord) -> str:
        """Format to a JSON string."""
        # yet another mypy type-check issue
        # https://github.com/python/mypy/issues/2900
        res: MutableMapping[str, Any] = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "fields": {
                "message": record.getMessage(),
            },
            "target": f"{self.prefix}::{record.filename}:{record.funcName}",
        }
        if record.exc_info:
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
            res["fields"]["exc_info"] = record.exc_text
        if record.stack_info:
            res["fields"]["stack_info"] = self.formatStack(record.stack_info)
        return json.dumps(res)


def use_log(level: int, formatter: logging.Formatter, logger_name: str):
    """Configure the global log."""
    logger = logging.getLogger(logger_name)
    logger.setLevel(level)
    if not logger.handlers:
        stream = logging.StreamHandler()
        stream.setFormatter(formatter)
        logger.addHandler(stream)
    return logger


def use_pretty_log(level: int = logging.DEBUG, prefix: str = "", logger_name: str = ""):
    """Enable colorful log."""
    return use_log(level, DebugFormat(prefix=prefix), logger_name)


def use_json_log(level: int = logging.INFO, prefix: str = "", logger_name: str = ""):
    """Enable JSON format log."""
    return use_log(level, JSONFormat(prefix=prefix), logger_name)


def get_logger(internal: bool = False):
    """Get the logger used by mosec for multiprocessing."""
    prefix = "mosec" if internal else "user"
    logger_name = MOSEC_LOG_NAME if internal else USER_LOG_NAME
    if os.environ.get(MOSEC_LOG_NAME, "") == str(logging.DEBUG):
        return use_pretty_log(prefix=prefix, logger_name=logger_name)
    return use_json_log(prefix=prefix, logger_name=logger_name)


def set_logger(debug=False):
    """Set the environment variable so all the sub-processes can inherit it."""
    if debug:
        os.environ[MOSEC_LOG_NAME] = str(logging.DEBUG)


# need to configure it here to make sure all the process can get the same one
set_logger(mosec_args.debug)
