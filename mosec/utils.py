from pydantic import BaseSettings


class Settings(BaseSettings):
    socket_prefix: str = "/tmp/mosec/"
    waitUtil: int = 10  # millisecond
    timeout: int = 3000  # millisecond
