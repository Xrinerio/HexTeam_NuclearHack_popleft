import json
from dataclasses import dataclass, field

from .type import Type


@dataclass
class KeyExchange:
    type: Type = field(default=Type.KEY_EXCHANGE, init=False)
    from_: str
    to: str
    public_key: str
    """Base64-encoded публичный ключ отправителя."""
    ttl: int = 16
    is_reply: bool = False
    """True если это ответ на KEY_EXCHANGE — получатель не должен отвечать ещё раз."""

    def to_bytes(self) -> bytes:
        return json.dumps(
            {
                "type": self.type.value,
                "from": self.from_,
                "to": self.to,
                "public_key": self.public_key,
                "ttl": self.ttl,
                "is_reply": self.is_reply,
            },
        ).encode()

    @classmethod
    def from_bytes(cls, data: bytes) -> "KeyExchange":
        d = json.loads(data)
        return cls(
            from_=d["from"],
            to=d["to"],
            public_key=d["public_key"],
            ttl=d.get("ttl", 16),
            is_reply=d.get("is_reply", False),
        )
