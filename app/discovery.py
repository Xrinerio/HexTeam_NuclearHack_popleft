import asyncio
import json
import socket
import time
import uuid

BROADCAST_ADDR = "255.255.255.255"
DISCOVERY_PORT = 50000
HELLO_INTERVAL = 2.0
PEER_TIMEOUT = 8.0


def get_local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return str(s.getsockname()[0])
    except Exception:  # noqa: BLE001
        return "127.0.0.1"


class Peer:
    __slots__ = ("ip", "last_seen", "name", "node_id", "port")

    def __init__(
        self,
        node_id: str,
        name: str,
        ip: str,
        port: int,
        last_seen: float,
    ) -> None:
        self.node_id = node_id
        self.name = name
        self.ip = ip
        self.port = port
        self.last_seen = last_seen

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "name": self.name,
            "ip": self.ip,
            "port": self.port,
            "last_seen": self.last_seen,
        }


class Discovery:
    def __init__(self, http_port: int = 8000) -> None:
        self.node_id = uuid.uuid4().hex[:12]
        self.name = socket.gethostname()
        self.ip = get_local_ip()
        self.http_port = http_port
        self.peers: dict[str, Peer] = {}
        self.start_time = time.time()
        self._running = False
        self._tasks: list[asyncio.Task] = []

    def get_me(self) -> dict:
        return {
            "node_id": self.node_id,
            "name": self.name,
            "ip": self.ip,
            "port": self.http_port,
        }

    def get_peers_list(self) -> list[dict]:
        return [p.to_dict() for p in self.peers.values()]

    async def start(self) -> None:
        self._running = True
        self._send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._send_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._tasks = [
            asyncio.create_task(self._sender()),
            asyncio.create_task(self._receiver()),
            asyncio.create_task(self._cleaner()),
        ]

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        self._send_sock.close()

    async def _sender(self) -> None:
        while self._running:
            try:
                packet = json.dumps(
                    {
                        "type": "hello",
                        "node_id": self.node_id,
                        "name": self.name,
                        "ip": self.ip,
                        "port": self.http_port,
                        "timestamp": time.time(),
                    },
                ).encode()
                self._send_sock.sendto(packet, (BROADCAST_ADDR, DISCOVERY_PORT))
            except OSError:
                pass
            await asyncio.sleep(HELLO_INTERVAL)

    async def _receiver(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", DISCOVERY_PORT))
        sock.setblocking(False)  # noqa: FBT003

        loop = asyncio.get_event_loop()
        while self._running:
            try:
                data = await loop.sock_recv(sock, 4096)
                self._handle_packet(data)
            except Exception:  # noqa: BLE001
                await asyncio.sleep(0.1)
        sock.close()

    async def _cleaner(self) -> None:
        while self._running:
            now = time.time()
            stale = [
                nid
                for nid, p in self.peers.items()
                if now - p.last_seen > PEER_TIMEOUT
            ]
            for nid in stale:
                del self.peers[nid]
            await asyncio.sleep(1.0)

    def _handle_packet(self, data: bytes) -> None:
        try:
            pkt = json.loads(data)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return
        if pkt.get("type") != "hello":
            return
        nid = pkt.get("node_id")
        if not nid or nid == self.node_id:
            return
        self.peers[nid] = Peer(
            node_id=nid,
            name=pkt.get("name", "?"),
            ip=pkt.get("ip", "?"),
            port=pkt.get("port", 0),
            last_seen=time.time(),
        )
