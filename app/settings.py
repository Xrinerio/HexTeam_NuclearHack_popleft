import uuid


class Settings:
    def __init__(self) -> None:
        self.NODE_ID = uuid.uuid4().hex[:12]
        self.BROADCAST_ADDR = "255.255.255.255"
        self.DISCOVERY_PORT = 50000
        self.HELLO_INTERVAL = 2.0
        self.PEER_TIMEOUT = 8.0
        self.HOST = "127.0.0.1"
        self.IDLE_TIMEOUT = 30.0
        self.DISCOVERY_INTERVAL = 3.0

settings = Settings()
