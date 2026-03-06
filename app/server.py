import asyncio
import json
import socket
from typing import Any

from app.core import logger


async def _handle_message(message: str) -> None:
    pass


class UDPBroadcastProtocol(asyncio.DatagramProtocol):
    def __init__(
        self,
        peer_id: str,
        name: str,
        discovery_interval: float,
        discovery_port: int,
    ) -> None:
        self.peer_id = peer_id
        self.name = name
        self.discovery_interval = discovery_interval
        self.discovery_port = discovery_port

        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport
        logger.info(
            f"UDP broadcast listener started on port {self.discovery_port}",
        )

    def datagram_received(self, data: bytes, addr: tuple) -> None:
        try:
            pkt = json.loads(data)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return

        if pkt.get("type") != "hello":
            return

        sender_id = pkt.get("peer_id")
        if sender_id == self.peer_id:
            return  # игнорируем свои пакеты

        name = pkt.get("name", "?")
        logger.info(
            f"[UDP] Broadcast from {addr}: peer_id={sender_id}, name={name}",
        )

        response = json.dumps(
            {
                "type": "hello",
                "peer_id": self.peer_id,
                "name": self.name,
            },
        ).encode()

        if self.transport:
            self.transport.sendto(response, addr)

    def error_received(self, exc: Exception) -> None:
        logger.error(f"[UDP] Error: {exc}")

    def connection_lost(self, _: Exception | None) -> None:
        logger.info("[UDP] Broadcast listener stopped")


class Server:
    def __init__(
        self,
        host: str,
        port: int,
        peer_id: str,
        discovery_interval: float,
        discovery_port: int,
        idle_timeout: float,
        broadcast_addr: str = "255.255.255.255",
    ) -> None:
        self.host = host
        self.port = port
        self.peer_id = peer_id
        self.discovery_interval = discovery_interval
        self.discovery_port = discovery_port
        self.idle_timeout = idle_timeout
        self.broadcast_addr = broadcast_addr
        self.server: asyncio.AbstractServer | None = None
        self._udp_transport: asyncio.DatagramTransport | None = None
        # активные TCP соединения: addr -> writer
        self._clients: dict[tuple, asyncio.StreamWriter] = {}
        # время последней активности: addr -> timestamp
        self._last_active: dict[tuple, float] = {}
        # известные ноды из UDP discovery: addr -> {"peer_id", "name"}
        self.peers: dict[tuple, dict] = {}
        self._tasks: list[asyncio.Task] = []

    async def start_server(self) -> None:
        logger.info(
            f"[Server] Starting TCP server on {self.host}:{self.port}...",
        )
        try:
            self.server = await asyncio.start_server(
                self.handle_request,
                self.host,
                self.port,
                reuse_address=True,
            )
        except OSError as e:
            logger.error(
                f"[Server] Failed to bind TCP on {self.host}:{self.port} — {e}",
            )
            raise
        addrs = ", ".join(str(s.getsockname()) for s in self.server.sockets)
        logger.info(f"[Server] TCP server running on {addrs}")

        logger.info(
            f"[Server] Starting UDP listener on port {self.discovery_port}...",
        )
        try:
            await self._start_udp_listener()
        except OSError as e:
            logger.error(
                f"[Server] Failed to bind UDP on port {self.discovery_port} — {e}",
            )
            raise
        logger.info("[Server] UDP listener started")

        self._tasks = [
            asyncio.create_task(self._broadcast_loop()),
            asyncio.create_task(self._idle_cleanup_loop()),
        ]
        logger.info(
            "[Server] Background tasks started (_broadcast_loop, _idle_cleanup_loop)",
        )

    async def stop_server(self) -> None:
        logger.info("[Server] Stopping...")

        for task in self._tasks:
            task.cancel()
        logger.info(f"[Server] Cancelled {len(self._tasks)} background tasks")

        if self._udp_transport:
            self._udp_transport.close()
            logger.info("[Server] UDP listener stopped")

        logger.info(
            f"[Server] Closing {len(self._clients)} active TCP connections...",
        )
        for writer in list(self._clients.values()):
            writer.close()
        self._clients.clear()

        if self.server:
            self.server.close()
            await self.server.wait_closed()
            logger.info("[Server] TCP server stopped")

    async def _start_udp_listener(self) -> None:
        loop = asyncio.get_running_loop()
        logger.debug(
            f"[UDP] Creating socket, binding to port {self.discovery_port}...",
        )

        udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        udp_sock.bind(("", self.discovery_port))
        logger.debug(f"[UDP] Socket bound to port {self.discovery_port}")

        self._udp_transport, _ = await loop.create_datagram_endpoint(
            lambda: UDPBroadcastProtocol(
                peer_id=self.peer_id,
                name=socket.gethostname(),
                discovery_interval=self.discovery_interval,
                discovery_port=self.discovery_port,
            ),
            sock=udp_sock,
        )

    async def _broadcast_loop(self) -> None:
        """Периодически рассылает UDP hello всем в сети."""
        pkt = json.dumps(
            {
                "type": "hello",
                "peer_id": self.peer_id,
                "name": socket.gethostname(),
                "port": self.port,
            },
        ).encode()

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind((self.broadcast_addr, 0))
        sock.setblocking(False)

        logger.debug("[UDP] _broadcast_loop started")
        try:
            while True:
                try:
                    await asyncio.get_running_loop().sock_sendto(
                        sock,
                        pkt,
                        (self.broadcast_addr, self.discovery_port),
                    )
                    logger.debug("[UDP] Broadcast sent")
                except OSError as e:
                    logger.error(f"[UDP] Failed to send broadcast: {e}")
                await asyncio.sleep(self.discovery_interval)
        except asyncio.CancelledError:
            logger.debug("[UDP] _broadcast_loop cancelled")
        finally:
            sock.close()
            logger.debug("[UDP] Broadcast socket closed")

    async def _connect(self, addr: tuple) -> asyncio.StreamWriter | None:
        """Открыть TCP-соединение к addr по требованию."""
        logger.info(f"[TCP] Connecting to {addr}...")
        try:
            reader, writer = await asyncio.open_connection(*addr)
            self._clients[addr] = writer
            self._last_active[addr] = asyncio.get_event_loop().time()
            task = asyncio.create_task(self.handle_request(reader, writer))
            self._tasks.append(task)
            logger.info(
                (
                    f"[TCP] Connected to {addr}"
                    f"(total clients: {len(self._clients)})"
                ),
            )
        except OSError as e:
            logger.error(f"[TCP] Failed to connect to {addr}: {e}")
            return None
        else:
            return writer

    async def _idle_cleanup_loop(self) -> None:
        """Закрывает TCP-соединения, простаивающие дольше idle_timeout."""
        logger.debug(
            (
                (
                    "[TCP] _idle_cleanup_loop started"
                    f"(timeout={self.idle_timeout}s,"
                    f"interval={self.idle_timeout / 2}s)"
                ),
            ),
        )
        try:
            while True:
                await asyncio.sleep(self.idle_timeout / 2)
                now = asyncio.get_event_loop().time()
                for addr in list(self._clients):
                    idle = now - self._last_active.get(addr, now)
                    if idle > self.idle_timeout:
                        logger.info(
                            (
                                f"[TCP] Closing idle connection to {addr}"
                                f"(idle {idle:.1f}s)"
                            ),
                        )
                        writer = self._clients.pop(addr, None)
                        self._last_active.pop(addr, None)
                        if writer and not writer.is_closing():
                            writer.close()
        except asyncio.CancelledError:
            logger.debug("[TCP] _idle_cleanup_loop cancelled")

    async def send(self, addr: tuple, data: str | bytes) -> None:
        """Отправить данные ноде. Соединение создаётся по требованию."""
        writer = self._clients.get(addr)
        if writer is None or writer.is_closing():
            writer = await self._connect(addr)
        if writer is None:
            return
        if isinstance(data, str):
            data = data.encode()
        writer.write(data)
        await writer.drain()
        self._last_active[addr] = asyncio.get_event_loop().time()

    async def handle_request(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        addr: tuple[Any, ...] = writer.get_extra_info("peername")
        self._clients[addr] = writer
        self._last_active[addr] = asyncio.get_event_loop().time()
        logger.info(f"[TCP] [+] Connected: {addr}")

        try:
            while True:
                data = await reader.read(1024)
                if not data:
                    break

                self._last_active[addr] = asyncio.get_event_loop().time()

                try:
                    message = data.decode("utf-8").strip()
                except UnicodeDecodeError:
                    logger.warning(
                        f"[TCP] [{addr}] Invalid UTF-8 data received",
                    )
                    continue

                logger.info(f"[TCP] [{addr}] >> {message}")
                await _handle_message(message)

        except (ConnectionResetError, ConnectionAbortedError):
            logger.warning(f"[TCP] [{addr}] Connection forcibly closed")
        except asyncio.IncompleteReadError:
            pass
        except OSError as e:
            logger.error(f"[TCP] [{addr}] OS error: {e}")
        finally:
            self._clients.pop(addr, None)
            self._last_active.pop(addr, None)
            logger.info(f"[TCP] [-] Disconnected: {addr}")
            writer.close()
            await writer.wait_closed()
