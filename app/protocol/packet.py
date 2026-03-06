import json
from dataclasses import asdict


class Packet:
    def to_bytes(self) -> bytes:
        data = asdict(self)
        data["type"] = data["type"].value

        return json.dumps(data).encode()

    @classmethod
    def from_bytes(cls, data: bytes) -> "Packet":
        return cls(**json.loads(data))
