from contextlib import ContextDecorator

from pydantic import BaseSettings


class Settings(BaseSettings):
    socket_prefix: str = "/tmp/mosec/"
    waitUtil: str = "10ms"
    timeout: str = "3s"


class SettingCtx(ContextDecorator):
    def __enter__(self):
        # export envs here
        return self

    def __exit__(self, *exc):
        # unset envs
        return False
