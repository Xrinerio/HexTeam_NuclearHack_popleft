import json
from dataclasses import dataclass, field

from .type import Type


@dataclass
class FileChunk:
    from_: str
    to: str
    file_id: str
    filename: str
    chunk_index: int
    total_chunks: int
    file_size: int
    sha256: str
    payload: str
    type: Type = field(default=Type.FILE_CHUNK, init=False)
    ttl: int = 16
    encrypted: bool = False

    def to_bytes(self) -> bytes:
        return json.dumps(
            {
                "type": self.type.value,
                "file_id": self.file_id,
                "from": self.from_,
                "to": self.to,
                "filename": self.filename,
                "chunk_index": self.chunk_index,
                "total_chunks": self.total_chunks,
                "file_size": self.file_size,
                "sha256": self.sha256,
                "payload": self.payload,
                "encrypted": self.encrypted,
                "ttl": self.ttl,
            },
        ).encode()

    @classmethod
    def from_bytes(cls, data: bytes) -> "FileChunk":
        d = json.loads(data)
        return cls(
            from_=d["from"],
            to=d["to"],
            file_id=d["file_id"],
            filename=d["filename"],
            chunk_index=d["chunk_index"],
            total_chunks=d["total_chunks"],
            file_size=d["file_size"],
            sha256=d["sha256"],
            payload=d["payload"],
            ttl=d.get("ttl", 16),
            encrypted=d.get("encrypted", False),
        )
