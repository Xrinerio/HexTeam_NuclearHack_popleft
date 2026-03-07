import os
from dataclasses import dataclass, field


@dataclass
class _Settings:
    # Идентификатор и имя текущего пира — загружаются из БД после регистрации.
    PEER_ID: str | None = field(default=None)
    USERNAME: str | None = field(default=None)
    # Main server settings
    PORT: int = 6767
    HOST: str = "0.0.0.0"
    # Uvicorn settings
    UVICORN_HOST: str = field(
        default_factory=lambda: os.environ.get("UVICORN_HOST", "127.0.0.1"),
    )
    UVICORN_PORT: int = 8001
    # Время в секундах, после которого неактивный пир считается offline и удаляется из списка пиров.
    IDLE_TIMEOUT: float = 20.0
    # Интервал между отправкой UDP broadcast сообщений для обнаружения пиров.
    DISCOVERY_INTERVAL: float = 3.0
    BROADCAST_ADDR: str = "255.255.255.255"
    # Порт для прослушивания UDP broadcast сообщений от других пиров.
    DISCOVERY_PORT: int = 50000
    # Максимальное время жизни недоставленного сообщения в секундах (по умолчанию 1 час).
    MESSAGE_TTL: int = 3600
    # Максимальное количество попыток переотправки сообщения.
    MESSAGE_MAX_RETRIES: int = 3
    # Размер одного чанка при передаче файлов (по умолчанию 32 КБ).
    FILE_CHUNK_SIZE: int = 32768
    # Директория для хранения данных файловых передач.
    FILES_DIR: str = "files/transfers"


Settings = _Settings()
