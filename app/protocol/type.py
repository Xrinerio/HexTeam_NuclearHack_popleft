from enum import Enum


class Type(Enum):
    """Типы сообщений."""

    MESSAGE = "MESSAGE"
    ACK = "ACK"
    ROUTES = "ROUTES"
    HELLO = "HELLO"
    PEER_INFO = "PEER_INFO"
    KEY_EXCHANGE = "KEY_EXCHANGE"
    FILE_CHUNK = "FILE_CHUNK"
    FILE_ACK = "FILE_ACK"
    PING = "PING"
    PONG = "PONG"
