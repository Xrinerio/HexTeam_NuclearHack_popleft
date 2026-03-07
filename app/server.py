import asyncio
import base64
import json
import socket
from typing import Any

from app.core import Settings, logger
from app.crypto.crypto import crypto
from app.network import routing
from app.protocol import KeyExchange, Type


def _our_public_key_b64() -> str:
    return base64.b64encode(bytes(crypto.public_key)).decode()  # type: ignore[arg-type]


async def _handle_peer_info(
    message: dict,
    addr: tuple,
) -> None:
    peer_id = message.get("peer_id")
    name = message.get("name", "?")
    port = message.get("port", 0)
    ip = addr[0]

    routing.add_neighbor(destination=peer_id, name=name, ip=ip, port=port)
    routes = message.get("routes")
    if routes is not None:
        routing.update_from_advertisement(
            gateway=peer_id,
            gateway_ip=ip,
            gateway_port=port,
            routes=routes,
        )


async def _handle_key_exchange(server: "Server", message: dict) -> None:
    from_id = message.get("from")
    to_id = message.get("to")
    public_key_b64 = message.get("public_key", "")
    ttl = message.get("ttl", 0)

    if to_id != server.peer_id:
        if ttl > 0:
            message["ttl"] = ttl - 1
            await server.send_to_peer(to_id, json.dumps(message).encode())
        return

    first_contact = from_id not in crypto.peers
    await crypto.add_peer(from_id, public_key_b64)
    logger.info(f"[Crypto] Stored public key of {from_id}")

    if first_contact and crypto.public_key is not None:
        kex = KeyExchange(
            from_=server.peer_id,
            to=from_id,
            public_key=_our_public_key_b64(),
        )
        await server.send_to_peer(from_id, kex.to_bytes())
        logger.info(f"[Crypto] KEY_EXCHANGE response sent to {from_id}")


async def _handle_message_packet(server: "Server", message: dict) -> None:
    from_id = message.get("from")
    to_id = message.get("to")
    ttl = message.get("ttl", 0)
    payload: str = message.get("payload", "")

    if to_id != server.peer_id:
        if ttl > 0:
            message["ttl"] = ttl - 1
            await server.send_to_peer(to_id, json.dumps(message).encode())
        else:
            logger.warning(f"[MSG] TTL=0, dropping id={message.get('id')}")
        return

    if not message.get("encrypted"):
        logger.warning(f"[MSG] Dropping unencrypted message from {from_id}")
        return

    try:
        decrypted = await crypto.decrypt_message_from(
            base64.b64decode(payload.encode()),
            from_id,
        )
        payload = decrypted.decode("utf-8")
        logger.info(f"[Crypto] Decrypted from {from_id}: {payload}")
    except Exception:  # noqa: BLE001
        logger.warning(
            f"[Crypto] Decrypt failed from {from_id}, dropping message",
        )
        return
    # deliver to chat (store in DB, push to WebSocket etc.)


async def _handle_message(
    server: "Server",
    message: dict[str, Any],
    addr: tuple,
) -> None:
    msg_type = message.get("type")

    if msg_type == Type.PEER_INFO.value:
        await _handle_peer_info(message, addr)
    elif msg_type == Type.KEY_EXCHANGE.value:
        await _handle_key_exchange(server, message)
    elif msg_type == Type.MESSAGE.value:
        await _handle_message_packet(server, message)


class UDPBroadcastProtocol(asyncio.DatagramProtocol):
    def __init__(
        self,
        discovery_interval: float,
        discovery_port: int,
        server: "Server",
    ) -> None:
        self.discovery_interval = discovery_interval
        self.discovery_port = discovery_port
        self.server = server
        self._futures: set[asyncio.Future] = set()
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport
        logger.info(
            f"UDP broadcast listener started on port {self.discovery_port}",
        )

    def datagram_received(self, data: bytes, addr: tuple) -> None:
        future = asyncio.ensure_future(self._handle_datagram(data, addr))
        self._futures.add(future)

    async def _handle_datagram(self, data: bytes, addr: tuple) -> None:
        try:
            pkt = json.loads(data)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return

        if pkt.get("type") != Type.HELLO.value:
            return

        sender_id = pkt.get("peer_id")
        if not self.server.peer_id or sender_id == self.server.peer_id:
            return

        name = pkt.get("name", "?")
        logger.debug(
            f"[UDP] Broadcast from {addr}: peer_id={sender_id}, name={name}",
        )

        # Тут начинается логика сохранения информации о близжайших пирах  # noqa: RUF003
        # Cтруктура pkt:  # noqa: RUF003
        #
        #     "type": "hello",        тип сообщения
        #     "peer_id": sender_id,   uuid пира
        #     "name": name,           hostname пира
        #     "port": tcp_port,       tcp порт пира
        #

        routing.add_neighbor(
            destination=sender_id,
            name=name,
            ip=addr[0],
            port=pkt.get("port", 0),
        )

        # Здесь сервер отправляет информацию о пирах по tcp в ответ на udp broadcast. # noqa: RUF003
        await self.server.send(
            addr=(addr[0], pkt.get("port")),
            data=json.dumps(
                {
                    "type": Type.PEER_INFO.value,
                    "peer_id": self.server.peer_id,
                    "name": Settings.USERNAME,  # or socket.gethostname(),
                    "port": self.server.port,
                    "routes": routing.get_advertisement(to_node_id=sender_id),
                },
            ),
            peer_id=sender_id,
        )

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
        discovery_interval: float = 2.0,
        discovery_port: int = 50000,
        idle_timeout: float = 20.0,
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
        self._clients: dict[tuple, asyncio.StreamWriter] = {}
        self._peer_ids: dict[tuple, str] = {}
        self._last_active: dict[tuple, float] = {}
        self._tasks: list[asyncio.Task] = []

    async def start_server(self) -> None:
        logger.debug(
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
        self._peer_ids.clear()

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
        udp_sock.bind(("0.0.0.0", self.discovery_port))
        logger.debug(f"[UDP] Socket bound to port {self.discovery_port}")

        self._udp_transport, _ = await loop.create_datagram_endpoint(
            lambda: UDPBroadcastProtocol(
                discovery_interval=self.discovery_interval,
                discovery_port=self.discovery_port,
                server=self,
            ),
            sock=udp_sock,
        )

    @staticmethod
    def _get_local_ips() -> list[str]:
        """Возвращает все локальные не-loopback IPv4 адреса."""
        ips: set[str] = set()
        for info in socket.getaddrinfo(
            socket.gethostname(),
            None,
            socket.AF_INET,
        ):
            ip = info[4][0]
            if not ip.startswith("127."):
                ips.add(ip)
        return list(ips)

    async def _broadcast_loop(self) -> None:
        """Периодически рассылает UDP hello через каждый сетевой интерфейс."""
        logger.debug("[UDP] _broadcast_loop started")
        socks: list[socket.socket] = []
        try:
            while True:
                for s in socks:
                    s.close()
                socks.clear()

                if not self.peer_id:
                    await asyncio.sleep(self.discovery_interval)
                    continue

                pkt = json.dumps(
                    {
                        "type": "HELLO",
                        "peer_id": self.peer_id,
                        "name": Settings.USERNAME or socket.gethostname(),
                        "port": self.port,
                    },
                ).encode()

                local_ips = self._get_local_ips()
                if not local_ips:
                    logger.warning("[UDP] No non-loopback interfaces found")
                    await asyncio.sleep(self.discovery_interval)
                    continue

                loop = asyncio.get_running_loop()
                for local_ip in local_ips:
                    try:
                        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                        sock.setsockopt(
                            socket.SOL_SOCKET,
                            socket.SO_BROADCAST,
                            1,
                        )
                        sock.bind((local_ip, 0))
                        sock.setblocking(False)  # noqa: FBT003
                        socks.append(sock)

                        await loop.sock_sendto(
                            sock,
                            pkt,
                            (self.broadcast_addr, self.discovery_port),
                        )
                        logger.debug(
                            f"[UDP] Broadcast sent via {local_ip}",
                        )
                    except OSError as e:
                        logger.error(
                            f"[UDP] Failed to send broadcast via {local_ip}: {e}",
                        )
                await asyncio.sleep(self.discovery_interval)
        except asyncio.CancelledError:
            logger.debug("[UDP] _broadcast_loop cancelled")
        finally:
            for s in socks:
                s.close()
            logger.debug("[UDP] Broadcast sockets closed")

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
                f"[TCP] Connected to {addr} (total clients: {len(self._clients)})",
            )
        except OSError as e:
            logger.error(f"[TCP] Failed to connect to {addr}: {e}")
            return None
        else:
            return writer

    async def _idle_cleanup_loop(self) -> None:
        """Закрывает TCP-соединения, простаивающие дольше idle_timeout."""
        try:
            while True:
                await asyncio.sleep(self.idle_timeout / 2)
                now = asyncio.get_event_loop().time()
                for addr in list(self._clients):
                    idle = now - self._last_active.get(addr, now)
                    if idle > self.idle_timeout:
                        writer = self._clients.pop(addr, None)
                        self._peer_ids.pop(addr, None)
                        self._last_active.pop(addr, None)
                        if writer and not writer.is_closing():
                            writer.close()
        except asyncio.CancelledError:
            logger.debug("[TCP] _idle_cleanup_loop cancelled")

    async def send(self, addr: tuple, data: str | bytes, peer_id: str) -> None:
        """Отправить данные ноде. Соединение создаётся по требованию."""
        writer = self._clients.get(addr)
        if writer is None or writer.is_closing():
            writer = await self._connect(addr)
        if writer is None:
            return
        self._peer_ids[addr] = peer_id
        if isinstance(data, str):
            data = data.encode()
        writer.write(data)
        await writer.drain()
        self._last_active[addr] = asyncio.get_event_loop().time()

    async def send_to_peer(self, peer_id: str, data: str | bytes) -> None:
        """Отправить данные пиру через таблицу маршрутизации."""
        addr = routing.get_next_hop_addr(peer_id)
        if addr is None:
            logger.warning(f"[TCP] Нет маршрута до {peer_id}")
            return
        route = routing.get_route(peer_id)
        gateway_id = route.gateway if route else peer_id
        await self.send(addr=addr, data=data, peer_id=gateway_id)

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
                    message = json.loads(data.decode("utf-8").strip())
                except (UnicodeDecodeError, json.JSONDecodeError):
                    logger.warning(f"[TCP] [{addr}] Invalid data received")
                    continue

                logger.debug(f"[TCP] [{addr}] >> {message}")
                await _handle_message(self, message, addr=addr)

        except (ConnectionResetError, ConnectionAbortedError):
            logger.warning(f"[TCP] [{addr}] Connection forcibly closed")
        except asyncio.IncompleteReadError:
            pass
        except OSError as e:
            logger.error(f"[TCP] [{addr}] OS error: {e}")
        finally:
            peer_id = self._peer_ids.get(addr)
            if peer_id is not None:
                routing.remove_routes_via(peer_id)
            logger.info(routing)
            self._clients.pop(addr, None)
            self._peer_ids.pop(addr, None)
            self._last_active.pop(addr, None)
            logger.info(f"[TCP] [-] Disconnected: {addr}")
            writer.close()
            await writer.wait_closed()
