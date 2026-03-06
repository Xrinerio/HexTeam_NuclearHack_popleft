class Peer:
    port: int = 6767

    def __init__(
        self,
        peer_id: str,
        name: str,
        ip: str | None,
    ) -> None:
        self.node_id = peer_id
        self.name = name
        self.ip = ip
