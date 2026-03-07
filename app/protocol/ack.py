import json
from dataclasses import dataclass, field

from .type import Type


@dataclass
class Ack:
    from_: str
    to: str
    message_id: str
    type: Type = field(default=Type.ACK, init=False)
    ttl: int = 16

    def to_bytes(self) -> bytes:
        return json.dumps(
            {
                "type": self.type.value,
                "from": self.from_,
                "to": self.to,
                "message_id": self.message_id,
                "ttl": self.ttl,
            },
        ).encode()

    @classmethod
    def from_bytes(cls, data: bytes) -> "Ack":
        d = json.loads(data)
        return cls(
            from_=d["from"],
            to=d["to"],
            message_id=d["message_id"],
            ttl=d.get("ttl", 16),
        )
