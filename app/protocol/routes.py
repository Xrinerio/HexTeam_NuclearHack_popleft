import json
from dataclasses import dataclass, field

from .type import Type


@dataclass
class _RouteEntry:
    destination: str
    hops: int


@dataclass
class Routes:
    type: Type = field(default=Type.ROUTES, init=False)
    from_: str
    routes: list[_RouteEntry]

    def to_bytes(self) -> bytes:
        return json.dumps(
            {
                "type": self.type.value,
                "from": self.from_,
                "routes": [
                    {"destination": r.destination, "hops": r.hops}
                    for r in self.routes
                ],
            },
        ).encode()

    @classmethod
    def from_bytes(cls, data: bytes) -> "Routes":
        d = json.loads(data)
        return cls(
            from_=d["from"],
            routes=[
                _RouteEntry(destination=r["destination"], hops=r["hops"])
                for r in d.get("routes", [])
            ],
        )
