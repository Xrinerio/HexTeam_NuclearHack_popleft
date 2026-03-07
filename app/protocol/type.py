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
    CALL_OFFER = "CALL_OFFER"
    CALL_ANSWER = "CALL_ANSWER"
    CALL_END = "CALL_END"
    CALL_AUDIO = "CALL_AUDIO"
