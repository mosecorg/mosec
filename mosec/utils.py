from pydantic import BaseSettings


class Settings(BaseSettings):
    socket_prefix: str = "/tmp/mosec/"
    waitUtil: str = "10ms"
    timeout: str = "3s"
