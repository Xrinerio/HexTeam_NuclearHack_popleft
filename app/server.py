import asyncio
import json
import socket

from app.core import logger, parse_message


class UDPBroadcastProtocol(asyncio.DatagramProtocol):
    def __init__(
        self,
        node_id: str,
        name: str,
        discovery_interval: float,
        discovery_port: int,
    ) -> None:
        self.node_id = node_id
        self.name = name
        self.discovery_interval = discovery_interval
        self.discovery_port = discovery_port

        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
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

        sender_id = pkt.get("node_id")
        if sender_id == self.node_id:
            return  # игнорируем свои пакеты

        name = pkt.get("name", "?")
        logger.info(
            f"[UDP] Broadcast from {addr}: node_id={sender_id}, name={name}",
        )

        response = json.dumps(
            {
                "type": "hello",
                "node_id": self.node_id,
                "name": self.name,
                "port": self.tcp_port,
            },
        ).encode()

        self.transport.sendto(response, addr)

    def error_received(self, exc: Exception) -> None:
        logger.error(f"[UDP] Error: {exc}")

    def connection_lost(self, _: Exception | None) -> None:
        logger.info("[UDP] Broadcast listener stopped")


class TCPServer:
    def __init__(
        self,
        host: str,
        port: int,
        node_id: str,
        discovery_interval: float,
        discovery_port: int,
        idle_timeout: float,
    ) -> None:
        self.host = host
        self.port = port
        self.node_id = node_id
        self.discovery_interval = discovery_interval
        self.discovery_port = discovery_port
        self.idle_timeout = idle_timeout
        self.server: asyncio.AbstractServer | None = None
        self._udp_transport: asyncio.DatagramTransport | None = None
        # активные TCP соединения: addr -> writer
        self._clients: dict[tuple, asyncio.StreamWriter] = {}
        # время последней активности: addr -> timestamp
        self._last_active: dict[tuple, float] = {}
        # известные ноды из UDP discovery: addr -> {"node_id", "name"}
        self.peers: dict[tuple, dict] = {}
        self._tasks: list[asyncio.Task] = []

    async def start_server(self) -> None:
        self.server = await asyncio.start_server(
            self.handle_request,
            self.host,
            self.port,
        )
        addrs = ", ".join(str(s.getsockname()) for s in self.server.sockets)
        logger.info(f"TCP Server running on {addrs}")

        await self._start_udp_listener()

        self._tasks = [
            asyncio.create_task(self._broadcast_loop()),
            asyncio.create_task(self._idle_cleanup_loop()),
        ]

    async def stop_server(self) -> None:
        for task in self._tasks:
            task.cancel()

        if self._udp_transport:
            self._udp_transport.close()
            logger.info("UDP listener stopped")

        for writer in list(self._clients.values()):
            writer.close()
        self._clients.clear()

        if self.server:
            self.server.close()
            await self.server.wait_closed()
            logger.info("TCP Server stopped")

    async def _start_udp_listener(self) -> None:
        loop = asyncio.get_running_loop()

        udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        udp_sock.bind(("", self.discovery_port))

        self._udp_transport, _ = await loop.create_datagram_endpoint(
            lambda: UDPBroadcastProtocol(
                node_id=self.node_id,
                name=socket.gethostname(),
                tcp_port=self.port,
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
                "node_id": self.node_id,
                "name": socket.gethostname(),
                "port": self.port,
            },
        ).encode()

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setblocking(False)

        try:
            while True:
                await asyncio.get_running_loop().sock_sendto(
                    sock,
                    pkt,
                    ("<broadcast>", self.discovery_port),
                )
                logger.debug("[UDP] Broadcast sent")
                await asyncio.sleep(self.discovery_interval)
        except asyncio.CancelledError:
            pass
        finally:
            sock.close()

    async def _connect(self, addr: tuple) -> asyncio.StreamWriter | None:
        """Открыть TCP-соединение к addr по требованию."""
        try:
            reader, writer = await asyncio.open_connection(*addr)
            self._clients[addr] = writer
            self._last_active[addr] = asyncio.get_event_loop().time()
            task = asyncio.create_task(self.handle_request(reader, writer))
            self._tasks.append(task)
            logger.info(f"[TCP] Connected to {addr}")
        except OSError as e:
            logger.error(f"[TCP] Failed to connect to {addr}: {e}")
            return None
        else:
            return writer

    async def _idle_cleanup_loop(self) -> None:
        """Закрывает TCP-соединения, простаивающие дольше IDLE_TIMEOUT."""
        try:
            while True:
                await asyncio.sleep(self.id / 2)
                now = asyncio.get_event_loop().time()
                for addr in list(self._clients):
                    if now - self._last_active.get(addr, now) > self.idle_timeout:
                        logger.info(f"[TCP] Closing idle connection to {addr}")
                        writer = self._clients.pop(addr, None)
                        self._last_active.pop(addr, None)
                        if writer and not writer.is_closing():
                            writer.close()
        except asyncio.CancelledError:
            logger.warning("Idle cleanup loop cancelled")

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
        addr = writer.get_extra_info("peername")
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
                await parse_message(message, addr, self)

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
