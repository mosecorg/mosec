import logging

from ._version import __version__  # noqa
from .server import Server
from .worker import Worker

__all__ = ["Server", "Worker"]

# setup library logging
logging.getLogger(__name__).addHandler(logging.NullHandler())
