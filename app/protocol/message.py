import json
import uuid
from dataclasses import dataclass, field

from app.core import utils

from .type import Type


@dataclass
class Message:
    from_: str
    to: str
    payload: str
    type: Type = field(default=Type.MESSAGE, init=False)
    id: str = field(default_factory=lambda: str(uuid.uuid4()), init=False)
    ttl: int = 16
    sent: int = field(default_factory=utils.now)
    encrypted: bool = False

    def to_bytes(self) -> bytes:
        return json.dumps(
            {
                "type": self.type.value,
                "id": self.id,
                "from": self.from_,
                "to": self.to,
                "ttl": self.ttl,
                "sent": self.sent,
                "encrypted": self.encrypted,
                "payload": self.payload,
            },
        ).encode()

    @classmethod
    def from_bytes(cls, data: bytes) -> "Message":
        d = json.loads(data)
        obj = cls(
            from_=d["from"],
            to=d["to"],
            ttl=d.get("ttl", 16),
            sent=d["sent"],
            payload=d["payload"],
            encrypted=d.get("encrypted", False),
        )
        obj.id = d["id"]
        return obj
