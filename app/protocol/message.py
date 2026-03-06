import json
import uuid
from dataclasses import dataclass, field

from app.core import utils

from .type import Type


@dataclass
class Message:
    type: Type = field(default=Type.MESSAGE, init=False)
    id: str = field(default_factory=lambda: str(uuid.uuid4()), init=False)
    from_: str
    to: str
    ttl: int = 16
    payload: str
    sent: int = field(default_factory=utils.now)

    def to_bytes(self) -> bytes:
        return json.dumps(
            {
                "type": self.type.value,
                "id": self.id,
                "from": self.from_,
                "to": self.to,
                "ttl": self.ttl,
                "sent": self.sent,
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
        )
        obj.id = d["id"]
        return obj
