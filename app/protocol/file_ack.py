import json
from dataclasses import dataclass, field

from .type import Type


@dataclass
class FileAck:
    from_: str
    to: str
    file_id: str
    chunk_index: int
    type: Type = field(default=Type.FILE_ACK, init=False)
    ttl: int = 16

    def to_bytes(self) -> bytes:
        return json.dumps(
            {
                "type": self.type.value,
                "from": self.from_,
                "to": self.to,
                "file_id": self.file_id,
                "chunk_index": self.chunk_index,
                "ttl": self.ttl,
            },
        ).encode()

    @classmethod
    def from_bytes(cls, data: bytes) -> "FileAck":
        d = json.loads(data)
        return cls(
            from_=d["from"],
            to=d["to"],
            file_id=d["file_id"],
            chunk_index=d["chunk_index"],
            ttl=d.get("ttl", 16),
        )
