import uuid
from dataclasses import dataclass


@dataclass
class Settings:
    PEER_ID: str = uuid.uuid4().hex[:12]
    BROADCAST_ADDR: str = "255.255.255.255"
    DISCOVERY_PORT: int = 50000
    HELLO_INTERVAL: float = 2.0
    PEER_TIMEOUT: float = 8.0
    HOST: str = "127.0.0.1"
    PORT: int = 6767
    UVICORN_PORT: int = 8001
    IDLE_TIMEOUT: float = 30.0
    DISCOVERY_INTERVAL: float = 3.0
