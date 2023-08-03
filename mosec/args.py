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

"""Command line arguments.

Arguments parsing for two parts:

    * prepared for the Rust service part
    * consumed by the Python worker part
"""

import argparse
import errno
import logging
import os
import random
import socket
import tempfile
import warnings

from mosec.env import get_env_namespace

DEFAULT_WAIT_MS = 10


def is_port_available(addr: str, port: int) -> bool:
    """Check if the port is available to use."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    err = sock.connect_ex((addr, port))
    sock.close()
    # https://docs.python.org/3/library/errno.html
    if err == 0:
        return False
    if err == errno.ECONNREFUSED:
        return True
    raise RuntimeError(
        f"Check {addr}:{port} socket connection err: {err}{errno.errorcode[err]}"
    )


def build_arguments_parser() -> argparse.ArgumentParser:
    """Build CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Mosec Server Configurations",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        epilog="The following arguments can be set through environment variables: ("
        "path, capacity, timeout, address, port, namespace, debug, log_level, dry_run"
        "). Note that the environment variable should start with `MOSEC_` with upper "
        "case. For example: `MOSEC_PORT=8080 MOSEC_TIMEOUT=5000 python main.py`.",
    )

    parser.add_argument(
        "--path",
        help=(
            "Unix Domain Socket address for internal Inter-Process Communication."
            "If not set, a random path will be created under the temporary dir."
        ),
        type=str,
        default=os.path.join(
            tempfile.gettempdir(), f"mosec_{random.randrange(2**32):x}"
        ),
    )

    parser.add_argument(
        "--capacity",
        help="Capacity of the request queue, beyond which new requests will be "
        "rejected with status 429",
        type=int,
        default=1024,
    )

    parser.add_argument(
        "--timeout",
        help="Service timeout for one request (milliseconds)",
        type=int,
        default=3000,
    )

    parser.add_argument(
        "--wait",
        help="[deprecated] Wait time for the batcher to batch (milliseconds)",
        type=int,
        default=DEFAULT_WAIT_MS,
    )

    parser.add_argument(
        "--address",
        help="Address of the HTTP service",
        type=str,
        default="0.0.0.0",
    )

    parser.add_argument(
        "--port",
        help="Port of the HTTP service",
        type=int,
        default=8000,
    )

    parser.add_argument(
        "--namespace",
        help="Namespace for prometheus metrics",
        type=str,
        default="mosec_service",
    )

    parser.add_argument(
        "--debug",
        help="Enable the service debug log",
        action="store_true",
    )

    parser.add_argument(
        "--log-level",
        help="Configure the service log level",
        choices=["debug", "info", "warning", "error"],
        default="info",
    )

    parser.add_argument(
        "--dry-run",
        help="Dry run the service with provided warmup examples (if any). "
        "This will omit the worker number for each stage.",
        action="store_true",
    )
    return parser


def parse_arguments() -> argparse.Namespace:
    """Parse user configurations."""
    parser = build_arguments_parser()
    args, _ = parser.parse_known_args(namespace=get_env_namespace())

    if args.wait != DEFAULT_WAIT_MS:
        warnings.warn(
            "`--wait` is deprecated and will be removed in v1, please configure"
            "the `max_wait_time` on `Server.append_worker`",
            DeprecationWarning,
        )

    if args.debug:
        args.log_level = "debug"
        warnings.warn(
            "`--debug` is deprecated and will be removed in v1, please configure"
            "`--log_level=debug`",
            DeprecationWarning,
        )

    if not is_port_available(args.address, args.port):
        raise RuntimeError(
            f"{args.address}:{args.port} is in use. "
            "Please change to a free one (use `--port`)."
        )

    return args


def get_log_level() -> int:
    """Check if the service is running in debug mode."""
    parser = build_arguments_parser()
    args, _ = parser.parse_known_args(namespace=get_env_namespace())
    if args.debug:
        return logging.DEBUG

    level_map = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
    }
    return level_map[args.log_level]
