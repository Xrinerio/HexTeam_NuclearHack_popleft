import json
from dataclasses import dataclass, field

from .type import Type


@dataclass
class Ack:
    type: Type = field(default=Type.ACK, init=False)
    message_id: str

    def to_bytes(self) -> bytes:
        return json.dumps(
            {
                "type": self.type.value,
                "message_id": self.message_id,
            },
        ).encode()

    @classmethod
    def from_bytes(cls, data: bytes) -> "Ack":
        d = json.loads(data)
        return cls(message_id=d["message_id"])
