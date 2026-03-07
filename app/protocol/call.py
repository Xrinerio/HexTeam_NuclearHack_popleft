import json
import uuid
from dataclasses import dataclass, field

from .type import Type


@dataclass
class CallOffer:
    from_: str
    to: str
    call_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: Type = field(default=Type.CALL_OFFER, init=False)
    ttl: int = 16

    def to_bytes(self) -> bytes:
        return json.dumps(
            {
                "type": self.type.value,
                "from": self.from_,
                "to": self.to,
                "call_id": self.call_id,
                "ttl": self.ttl,
            },
        ).encode()


@dataclass
class CallAnswer:
    from_: str
    to: str
    call_id: str
    accepted: bool
    type: Type = field(default=Type.CALL_ANSWER, init=False)
    ttl: int = 16

    def to_bytes(self) -> bytes:
        return json.dumps(
            {
                "type": self.type.value,
                "from": self.from_,
                "to": self.to,
                "call_id": self.call_id,
                "accepted": self.accepted,
                "ttl": self.ttl,
            },
        ).encode()


@dataclass
class CallEnd:
    from_: str
    to: str
    call_id: str
    type: Type = field(default=Type.CALL_END, init=False)
    ttl: int = 16

    def to_bytes(self) -> bytes:
        return json.dumps(
            {
                "type": self.type.value,
                "from": self.from_,
                "to": self.to,
                "call_id": self.call_id,
                "ttl": self.ttl,
            },
        ).encode()


@dataclass
class CallAudio:
    from_: str
    to: str
    call_id: str
    seq: int
    payload: str
    type: Type = field(default=Type.CALL_AUDIO, init=False)
    encrypted: bool = True
    ttl: int = 16

    def to_bytes(self) -> bytes:
        return json.dumps(
            {
                "type": self.type.value,
                "from": self.from_,
                "to": self.to,
                "call_id": self.call_id,
                "seq": self.seq,
                "payload": self.payload,
                "encrypted": self.encrypted,
                "ttl": self.ttl,
            },
        ).encode()
