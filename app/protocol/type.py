from enum import Enum


class Type(Enum):
    """Типы сообщений."""

    MESSAGE = "MESSAGE"
    ACK = "ACK"
    ROUTES = "ROUTES"
