import json
from dataclasses import dataclass, field

from .type import Type


@dataclass
class Ping:
    from_: str
    to: str
    ping_id: str
    timestamp: float
    type: Type = field(default=Type.PING, init=False)
    ttl: int = 16

    def to_bytes(self) -> bytes:
        return json.dumps(
            {
                "type": self.type.value,
                "from": self.from_,
                "to": self.to,
                "ping_id": self.ping_id,
                "timestamp": self.timestamp,
                "ttl": self.ttl,
            },
        ).encode()

    @classmethod
    def from_bytes(cls, data: bytes) -> "Ping":
        d = json.loads(data)
        return cls(
            from_=d["from"],
            to=d["to"],
            ping_id=d["ping_id"],
            timestamp=d["timestamp"],
            ttl=d.get("ttl", 16),
        )


@dataclass
class Pong:
    from_: str
    to: str
    ping_id: str
    ping_timestamp: float
    pong_timestamp: float
    type: Type = field(default=Type.PONG, init=False)
    ttl: int = 16

    def to_bytes(self) -> bytes:
        return json.dumps(
            {
                "type": self.type.value,
                "from": self.from_,
                "to": self.to,
                "ping_id": self.ping_id,
                "ping_timestamp": self.ping_timestamp,
                "pong_timestamp": self.pong_timestamp,
                "ttl": self.ttl,
            },
        ).encode()

    @classmethod
    def from_bytes(cls, data: bytes) -> "Pong":
        d = json.loads(data)
        return cls(
            from_=d["from"],
            to=d["to"],
            ping_id=d["ping_id"],
            ping_timestamp=d["ping_timestamp"],
            pong_timestamp=d["pong_timestamp"],
            ttl=d.get("ttl", 16),
        )
