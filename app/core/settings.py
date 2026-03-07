import uuid
from dataclasses import dataclass


@dataclass
class Settings:
    # Уникальный идентификатор пира, генерируется при каждом запуске. Нужно будет сохранять.
    PEER_ID: str = str(uuid.uuid4())
    # Main server settings
    PORT: int = 6767
    HOST: str = "0.0.0.0"
    # Uvicorn settings
    UVICORN_HOST: str = "127.0.0.1"
    UVICORN_PORT: int = 8001
    # Время в секундах, после которого неактивный пир считается offline и удаляется из списка пиров.
    IDLE_TIMEOUT: float = 30.0
    # Интервал между отправкой UDP broadcast сообщений для обнаружения пиров.
    DISCOVERY_INTERVAL: float = 3.0
    BROADCAST_ADDR: str = "255.255.255.255"
    # Порт для прослушивания UDP broadcast сообщений от других пиров.
    DISCOVERY_PORT: int = 50000
