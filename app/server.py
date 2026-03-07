import asyncio
import base64
import hashlib
import json
import socket
from pathlib import Path
from typing import Any

from app.core import Settings, logger, utils
from app.crud.file_transfers import (
    cleanup_expired_transfers,
    complete_file_transfer,
    create_file_transfer,
    fail_file_transfer,
    get_file_transfer,
    get_undelivered_chunks,
    increment_chunk_retry,
    increment_received_chunks,
    mark_chunk_delivered,
)
from app.crud.messages import (
    delete_expired_undelivered,
    get_undelivered_outgoing,
    increment_retry_count,
    mark_delivered,
    save_message,
)
from app.crud.users import save_peer_name
from app.crypto.crypto import crypto
from app.network.buffer import buffer
from app.network.routing import routing
from app.network.ws_manager import ws_manager
from app.protocol import (
    Ack,
    FileAck,
    FileChunk,
    KeyExchange,
    Message,
    Pong,
    Type,
)


def _our_public_key_b64() -> str:
    return base64.b64encode(bytes(crypto.public_key)).decode()  # type: ignore[arg-type]


async def _handle_peer_info(
    server: "Server",
    message: dict,
    addr: tuple,
) -> None:
    peer_id = message.get("peer_id")
    name = message.get("name", "?")
    port = message.get("port", 0)
    ip = addr[0]

    routing.add_neighbor(destination=peer_id, name=name, ip=ip, port=port)

    # Bind addr → peer_id so that when the TCP connection drops (handle_request
    # finally-block), remove_routes_via is called even for incoming connections.
    server.register_peer_addr(addr, peer_id)

    # Persist peer name in users table
    if peer_id and name:
        save_peer_name(peer_id, name)

    routes = message.get("routes")
    if routes is not None:
        routing.update_from_advertisement(
            gateway=peer_id,
            gateway_ip=ip,
            gateway_port=port,
            routes=routes,
        )

    await _flush_buffer(server)


async def _flush_buffer(server: "Server") -> None:
    """Отправляет буферизованные пакеты для появившихся маршрутов."""
    for destination in buffer.get_pending_destinations():
        if routing.get_next_hop_addr(destination) is not None:
            packets = buffer.pop_all(destination)
            for data in packets:
                await server.send_to_peer(destination, data)
            logger.info(
                f"[Buffer] Flushed {len(packets)} packet(s) to {destination}",
            )


async def _handle_key_exchange(server: "Server", message: dict) -> None:
    from_id = message.get("from")
    to_id = message.get("to")
    public_key_b64 = message.get("public_key", "")
    ttl = message.get("ttl", 0)
    is_reply = message.get("is_reply", False)

    if to_id != server.peer_id:
        if ttl > 0:
            message["ttl"] = ttl - 1
            data = json.dumps(message).encode()
            if routing.get_next_hop_addr(to_id) is not None:
                await server.send_to_peer(to_id, data)
            else:
                buffer.add(to_id, data)
                logger.debug(
                    f"[Buffer] No route to {to_id}, buffered KEY_EXCHANGE",
                )
        return

    # Detect if the key is new or changed
    existing = crypto.peers.get(from_id)
    new_key_bytes = base64.b64decode(public_key_b64)
    key_changed = existing is None or bytes(existing) != new_key_bytes

    await crypto.add_peer(from_id, public_key_b64)
    if key_changed:
        logger.info(
            f"[Crypto] Stored {'new' if existing is None else 'updated'} public key of {from_id}",
        )
    else:
        logger.debug(f"[Crypto] Received unchanged public key of {from_id}")

    # Always respond to non-reply KEY_EXCHANGEs so both sides stay in sync.
    # is_reply=True prevents an infinite ping-pong loop.
    if not is_reply and crypto.public_key is not None:
        kex = KeyExchange(
            from_=server.peer_id,
            to=from_id,
            public_key=_our_public_key_b64(),
            is_reply=True,
        )
        await server.send_to_peer(from_id, kex.to_bytes())
        logger.info(f"[Crypto] KEY_EXCHANGE reply sent to {from_id}")


async def _handle_message_packet(server: "Server", message: dict) -> None:
    from_id = message.get("from")
    to_id = message.get("to")
    ttl = message.get("ttl", 0)
    payload: str = message.get("payload", "")

    if to_id != server.peer_id:
        if ttl > 0:
            message["ttl"] = ttl - 1
            data = json.dumps(message).encode()
            if routing.get_next_hop_addr(to_id) is not None:
                await server.send_to_peer(to_id, data)
            else:
                buffer.add(to_id, data)
                logger.debug(
                    f"[Buffer] No route to {to_id}, buffered MESSAGE",
                )
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
        # Stale key — ask the remote peer to re-exchange keys
        if (
            routing.get_next_hop_addr(from_id) is not None
            and server.peer_id
            and crypto.public_key is not None
        ):
            kex = KeyExchange(
                from_=server.peer_id,
                to=from_id,
                public_key=_our_public_key_b64(),
            )
            await server.send_to_peer(from_id, kex.to_bytes())
            logger.info(
                f"[Crypto] Sent KEY_EXCHANGE to {from_id} after decrypt failure",
            )
        return

    # send ACK back to sender
    message_id = message.get("id", "")
    ack = Ack(
        from_=server.peer_id,
        to=from_id,
        message_id=message_id,
    )
    await server.send_to_peer(from_id, ack.to_bytes())
    logger.info(f"[ACK] Sent ACK for message {message_id} to {from_id}")

    # Store incoming message in DB and push to frontend via WebSocket
    saved = save_message(
        message_id=message_id,
        from_peer_id=from_id,
        to_peer_id=server.peer_id,
        content=payload,
        is_outgoing=False,
        created_at=message.get("sent", utils.now()),
    )
    await ws_manager.broadcast("new_message", saved)


async def _handle_ack(server: "Server", message: dict) -> None:
    from_id = message.get("from")
    to_id = message.get("to")
    message_id = message.get("message_id", "")
    ttl = message.get("ttl", 0)

    if to_id != server.peer_id:
        if ttl > 0:
            message["ttl"] = ttl - 1
            data = json.dumps(message).encode()
            if routing.get_next_hop_addr(to_id) is not None:
                await server.send_to_peer(to_id, data)
            else:
                buffer.add(to_id, data)
                logger.debug(
                    f"[Buffer] No route to {to_id}, buffered ACK",
                )
        else:
            logger.warning(
                f"[ACK] TTL=0, dropping ACK for message {message_id}",
            )
        return

    logger.info(
        f"[ACK] Message {message_id} successfully delivered to {from_id}",
    )

    # Mark message as delivered in DB and notify frontend
    if mark_delivered(message_id):
        await ws_manager.broadcast(
            "message_delivered",
            {"message_id": message_id},
        )


def _reassemble_file(
    transfer_dir: Path,
    total_chunks: int,
) -> bytes | None:
    """Reassemble file chunks into the complete file."""
    parts = []
    for i in range(total_chunks):
        chunk_path = transfer_dir / f"chunk_{i}"
        if not chunk_path.exists():
            return None
        parts.append(chunk_path.read_bytes())
    return b"".join(parts)


async def _save_and_finalize_chunk(
    server: "Server",
    message: dict,
    decrypted: bytes,
) -> None:
    """Сохраняет чанк на диск и финализирует передачу если все чанки получены."""
    file_id = message["file_id"]
    transfer_dir = Path(Settings.FILES_DIR) / file_id
    transfer_dir.mkdir(parents=True, exist_ok=True)
    chunk_path = transfer_dir / f"chunk_{message['chunk_index']}"

    if chunk_path.exists():
        return

    chunk_path.write_bytes(decrypted)

    if get_file_transfer(file_id) is None:
        create_file_transfer(
            file_id=file_id,
            from_peer_id=message["from"],
            to_peer_id=server.peer_id,
            filename=message.get("filename", ""),
            file_size=message.get("file_size", 0),
            sha256=message.get("sha256", ""),
            total_chunks=message.get("total_chunks", 0),
            is_outgoing=False,
        )

    total = message.get("total_chunks", 0)
    received = increment_received_chunks(file_id)
    logger.info(
        f"[FILE] Chunk {message['chunk_index']}/{total - 1} "
        f"of {file_id} ({received}/{total})",
    )

    if received < total:
        return

    assembled = _reassemble_file(transfer_dir, total)
    if assembled is None:
        return

    actual = hashlib.sha256(assembled).hexdigest()
    expected = message.get("sha256", "")
    if actual == expected:
        (transfer_dir / "complete").write_bytes(assembled)
        complete_file_transfer(file_id)
        logger.info(f"[FILE] {file_id} received and verified")
        await ws_manager.broadcast(
            "file_received",
            {
                "file_id": file_id,
                "filename": message.get("filename", ""),
                "file_size": message.get("file_size", 0),
                "from_peer_id": message["from"],
            },
        )
    else:
        logger.error(f"[FILE] Hash mismatch for {file_id}")
        fail_file_transfer(file_id)


async def _handle_file_chunk(server: "Server", message: dict) -> None:
    to_id = message.get("to")
    ttl = message.get("ttl", 0)

    if to_id != server.peer_id:
        if ttl > 0:
            message["ttl"] = ttl - 1
            data = json.dumps(message).encode()
            if routing.get_next_hop_addr(to_id) is not None:
                await server.send_to_peer(to_id, data)
            else:
                buffer.add(to_id, data)
                logger.debug(
                    f"[Buffer] No route to {to_id}, buffered FILE_CHUNK",
                )
        return

    if not message.get("encrypted"):
        logger.warning(
            f"[FILE] Dropping unencrypted chunk from {message.get('from')}",
        )
        return

    try:
        decrypted = await crypto.decrypt_message_from(
            base64.b64decode(message["payload"].encode()),
            message["from"],
        )
    except Exception:  # noqa: BLE001
        logger.warning(
            f"[FILE] Decrypt failed for chunk "
            f"{message.get('chunk_index')} of {message.get('file_id')}",
        )
        # Stale key — ask the remote peer to re-exchange keys
        chunk_from = message.get("from")
        if (
            chunk_from
            and routing.get_next_hop_addr(chunk_from) is not None
            and server.peer_id
            and crypto.public_key is not None
        ):
            kex = KeyExchange(
                from_=server.peer_id,
                to=chunk_from,
                public_key=_our_public_key_b64(),
            )
            await server.send_to_peer(chunk_from, kex.to_bytes())
            logger.info(
                f"[Crypto] Sent KEY_EXCHANGE to {chunk_from} after file decrypt failure",
            )
        return

    await _save_and_finalize_chunk(server, message, decrypted)

    file_id = message["file_id"]
    # ACK this chunk regardless (idempotent)
    ack = FileAck(
        from_=server.peer_id,
        to=message["from"],
        file_id=file_id,
        chunk_index=message.get("chunk_index", 0),
    )
    await server.send_to_peer(message["from"], ack.to_bytes())


async def _handle_file_ack(server: "Server", message: dict) -> None:
    to_id = message.get("to")
    file_id = message.get("file_id", "")
    chunk_index = message.get("chunk_index", 0)
    ttl = message.get("ttl", 0)

    if to_id != server.peer_id:
        if ttl > 0:
            message["ttl"] = ttl - 1
            data = json.dumps(message).encode()
            if routing.get_next_hop_addr(to_id) is not None:
                await server.send_to_peer(to_id, data)
            else:
                buffer.add(to_id, data)
                logger.debug(
                    f"[Buffer] No route to {to_id}, buffered FILE_ACK",
                )
        return

    logger.info(
        f"[FILE_ACK] Chunk {chunk_index} of {file_id} acknowledged",
    )

    mark_chunk_delivered(file_id, chunk_index)
    transfer = get_file_transfer(file_id)
    if transfer and transfer["status"] == "completed":
        logger.info(f"[FILE] Transfer {file_id} fully delivered")
        await ws_manager.broadcast(
            "file_transfer_completed",
            {
                "file_id": file_id,
                "filename": transfer["filename"],
                "to_peer_id": transfer["to_peer_id"],
            },
        )


async def _handle_ping(server: "Server", message: dict) -> None:
    to_id = message.get("to")
    ttl = message.get("ttl", 0)

    if to_id != server.peer_id:
        if ttl > 0:
            message["ttl"] = ttl - 1
            await server.send_to_peer(to_id, json.dumps(message).encode())
        return

    pong = Pong(
        from_=server.peer_id,
        to=message["from"],
        ping_id=message["ping_id"],
        ping_timestamp=message["timestamp"],
        pong_timestamp=utils.now_ms(),
    )
    await server.send_to_peer(message["from"], pong.to_bytes())
    logger.info(
        f"[PING] Received ping {message['ping_id']} from {message['from']}, pong sent",
    )


async def _handle_pong(server: "Server", message: dict) -> None:
    to_id = message.get("to")
    ttl = message.get("ttl", 0)

    if to_id != server.peer_id:
        if ttl > 0:
            message["ttl"] = ttl - 1
            await server.send_to_peer(to_id, json.dumps(message).encode())
        return

    ping_id = message["ping_id"]
    future = server.pending_pings.pop(ping_id, None)
    if future and not future.done():
        future.set_result(message)
        logger.info(f"[PONG] Received pong {ping_id} from {message['from']}")


async def _handle_call_offer(server: "Server", message: dict) -> None:
    to_id = message.get("to")
    ttl = message.get("ttl", 0)

    if to_id != server.peer_id:
        if ttl > 0:
            message["ttl"] = ttl - 1
            data = json.dumps(message).encode()
            if routing.get_next_hop_addr(to_id) is not None:
                await server.send_to_peer(to_id, data)
            else:
                buffer.add(to_id, data)
        return

    call_id = message["call_id"]
    from_id = message["from"]
    server.active_calls[call_id] = {
        "peer_a": from_id,
        "peer_b": server.peer_id,
        "started_at": utils.now(),
    }
    await ws_manager.broadcast(
        "call_offer",
        {"call_id": call_id, "from_peer_id": from_id},
    )
    logger.info(f"[CALL] Incoming call offer {call_id} from {from_id}")


async def _handle_call_answer(server: "Server", message: dict) -> None:
    to_id = message.get("to")
    ttl = message.get("ttl", 0)

    if to_id != server.peer_id:
        if ttl > 0:
            message["ttl"] = ttl - 1
            data = json.dumps(message).encode()
            if routing.get_next_hop_addr(to_id) is not None:
                await server.send_to_peer(to_id, data)
        return

    call_id = message["call_id"]
    accepted = message.get("accepted", False)
    if not accepted:
        server.active_calls.pop(call_id, None)
    await ws_manager.broadcast(
        "call_answer",
        {
            "call_id": call_id,
            "from_peer_id": message["from"],
            "accepted": accepted,
        },
    )
    logger.info(
        f"[CALL] Call {call_id} {'accepted' if accepted else 'rejected'} "
        f"by {message['from']}",
    )


async def _handle_call_end(server: "Server", message: dict) -> None:
    to_id = message.get("to")
    ttl = message.get("ttl", 0)

    if to_id != server.peer_id:
        if ttl > 0:
            message["ttl"] = ttl - 1
            data = json.dumps(message).encode()
            if routing.get_next_hop_addr(to_id) is not None:
                await server.send_to_peer(to_id, data)
        return

    call_id = message["call_id"]
    server.active_calls.pop(call_id, None)
    await ws_manager.broadcast(
        "call_ended",
        {"call_id": call_id, "from_peer_id": message["from"]},
    )
    logger.info(f"[CALL] Call {call_id} ended by {message['from']}")


async def _handle_call_audio(server: "Server", message: dict) -> None:
    to_id = message.get("to")
    ttl = message.get("ttl", 0)

    if to_id != server.peer_id:
        if ttl > 0:
            message["ttl"] = ttl - 1
            data = json.dumps(message).encode()
            if routing.get_next_hop_addr(to_id) is not None:
                await server.send_to_peer(to_id, data)
        return

    call_id = message.get("call_id", "")
    if call_id not in server.active_calls:
        return

    if not message.get("encrypted"):
        return

    try:
        decrypted = await crypto.decrypt_message_from(
            base64.b64decode(message["payload"].encode()),
            message["from"],
        )
        audio_b64 = base64.b64encode(decrypted).decode()
    except Exception:  # noqa: BLE001
        return

    await ws_manager.broadcast(
        "call_audio",
        {
            "call_id": call_id,
            "seq": message.get("seq", 0),
            "audio": audio_b64,
        },
    )


async def _handle_message(
    server: "Server",
    message: dict[str, Any],
    addr: tuple,
) -> None:
    msg_type = message.get("type")

    if msg_type == Type.PEER_INFO.value:
        await _handle_peer_info(server, message, addr)
    elif msg_type == Type.KEY_EXCHANGE.value:
        await _handle_key_exchange(server, message)
    elif msg_type == Type.MESSAGE.value:
        await _handle_message_packet(server, message)
    elif msg_type == Type.ACK.value:
        await _handle_ack(server, message)
    elif msg_type == Type.FILE_CHUNK.value:
        await _handle_file_chunk(server, message)
    elif msg_type == Type.FILE_ACK.value:
        await _handle_file_ack(server, message)
    elif msg_type == Type.PING.value:
        await _handle_ping(server, message)
    elif msg_type == Type.PONG.value:
        await _handle_pong(server, message)
    elif msg_type == Type.CALL_OFFER.value:
        await _handle_call_offer(server, message)
    elif msg_type == Type.CALL_ANSWER.value:
        await _handle_call_answer(server, message)
    elif msg_type == Type.CALL_END.value:
        await _handle_call_end(server, message)
    elif msg_type == Type.CALL_AUDIO.value:
        await _handle_call_audio(server, message)


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

        # Не добавляем соседа здесь: получение UDP broadcast не гарантирует
        # возможность TCP-связи (например, при firewall-блокировке).
        # Сосед будет добавлен в _handle_peer_info при успешном TCP-обмене.

        target_addr = (addr[0], pkt.get("port"))
        peer_info_data = json.dumps(
            {
                "type": Type.PEER_INFO.value,
                "peer_id": self.server.peer_id,
                "name": Settings.USERNAME,
                "port": self.server.port,
                "routes": routing.get_advertisement(to_node_id=sender_id),
            },
        )

        # Если пир уже известен — отправляем через существующее TCP-соединение.
        # Если нет — пробуем подключиться ОДИН раз (без ретраев).
        # Это позволяет найти нового соседа, но не блокирует event loop
        # длительными ретраями при firewall-блокировке.
        if routing.get_route(sender_id) is not None:
            await self.server.send(
                addr=target_addr,
                data=peer_info_data,
                peer_id=sender_id,
            )
        else:
            # Первый контакт: одна попытка TCP без ретраев
            saved = self.server.send_retries
            self.server.send_retries = 1
            try:
                await self.server.send(
                    addr=target_addr,
                    data=peer_info_data,
                    peer_id=sender_id,
                )
            finally:
                self.server.send_retries = saved

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
        send_retries: int = 3,
        retry_delay: float = 1.0,
        resend_interval: float = 10.0,
    ) -> None:
        self.host = host
        self.port = port
        self.peer_id = peer_id
        self.discovery_interval = discovery_interval
        self.discovery_port = discovery_port
        self.idle_timeout = idle_timeout
        self.broadcast_addr = broadcast_addr
        self.send_retries = send_retries
        self.retry_delay = retry_delay
        self.resend_interval = resend_interval
        self.server: asyncio.AbstractServer | None = None
        self._udp_transport: asyncio.DatagramTransport | None = None
        self._clients: dict[tuple, asyncio.StreamWriter] = {}
        self._peer_ids: dict[tuple, str] = {}
        self._last_active: dict[tuple, float] = {}
        self._tasks: list[asyncio.Task] = []
        self.pending_pings: dict[str, asyncio.Future] = {}
        self.active_calls: dict[str, dict] = {}

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
            # Disable Nagle on listening sockets
            for s in self.server.sockets:
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
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
            asyncio.create_task(self._resend_undelivered_loop()),
            asyncio.create_task(self._resend_file_chunks_loop()),
            asyncio.create_task(self._keepalive_loop()),
        ]
        logger.info("[Server] Background tasks started")

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
            sock = writer.get_extra_info("socket")
            if sock is not None:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
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
                        idle_peer_id = self._peer_ids.pop(addr, None)
                        self._last_active.pop(addr, None)
                        if idle_peer_id:
                            routing.remove_routes_via(idle_peer_id)
                        if writer and not writer.is_closing():
                            writer.close()
        except asyncio.CancelledError:
            logger.debug("[TCP] _idle_cleanup_loop cancelled")

    async def _keepalive_loop(self) -> None:
        """Периодически отправляет PEER_INFO прямым соседям по уже открытым
        TCP-соединениям, чтобы read-timeout на обеих сторонах не срабатывал.

        Важно: используем _peer_ids (addr → peer_id), а не routing-таблицу —
        это гарантирует запись в существующий TCP-сокет, а не в новое
        соединение на server-port соседа.
        """
        interval = max(5.0, self.idle_timeout / 4)
        try:
            while True:
                await asyncio.sleep(interval)
                if not self.peer_id:
                    continue
                # Снимаем снимок, чтобы не итерироваться по изменяющемуся словарю
                for addr, peer_id in list(self._peer_ids.items()):
                    route = routing.get_route(peer_id)
                    if route is None or route.hops != 1:
                        continue
                    writer = self._clients.get(addr)
                    if writer is None or writer.is_closing():
                        continue
                    peer_info = json.dumps(
                        {
                            "type": Type.PEER_INFO.value,
                            "peer_id": self.peer_id,
                            "name": Settings.USERNAME,
                            "port": self.port,
                            "routes": routing.get_advertisement(
                                to_node_id=peer_id,
                            ),
                        },
                    ).encode()
                    if not peer_info.endswith(b"\n"):
                        peer_info += b"\n"
                    try:
                        writer.write(peer_info)
                        await writer.drain()
                        self._last_active[addr] = (
                            asyncio.get_event_loop().time()
                        )
                        logger.debug(
                            f"[Keepalive] Sent PEER_INFO to {peer_id} via {addr}",
                        )
                    except Exception:  # noqa: BLE001
                        pass
        except asyncio.CancelledError:
            logger.debug("[Keepalive] _keepalive_loop cancelled")

    async def _resend_undelivered_loop(self) -> None:
        """Периодически переотправляет недоставленные исходящие сообщения."""
        try:
            while True:
                await asyncio.sleep(self.resend_interval)
                if not self.peer_id:
                    continue

                # Clean up expired / exhausted messages
                deleted = delete_expired_undelivered(
                    ttl=Settings.MESSAGE_TTL,
                    max_retries=Settings.MESSAGE_MAX_RETRIES,
                )
                if deleted:
                    logger.info(
                        f"[Resend] Deleted {deleted} expired/exhausted "
                        f"undelivered message(s)",
                    )

                pending = get_undelivered_outgoing()
                if not pending:
                    continue

                logger.info(
                    f"[Resend] {len(pending)} undelivered message(s) found",
                )

                for row in pending:
                    to_id = row["to_peer_id"]
                    increment_retry_count(row["message_id"])

                    if routing.get_route(to_id) is None:
                        logger.debug(
                            f"[Resend] No route to {to_id}, "
                            f"skipping {row['message_id']} "
                            f"(attempt {row['retry_count'] + 1})",
                        )
                        continue
                    if to_id not in crypto.peers:
                        logger.debug(
                            f"[Resend] No key for {to_id}, "
                            f"skipping {row['message_id']} "
                            f"(attempt {row['retry_count'] + 1})",
                        )
                        continue

                    try:
                        raw = await crypto.encrypt_message_to(
                            row["content"].encode(),
                            to_id,
                        )
                    except Exception:  # noqa: BLE001
                        logger.warning(
                            f"[Resend] Encrypt failed for {row['message_id']}",
                        )
                        continue

                    msg = Message(
                        from_=self.peer_id,
                        to=to_id,
                        payload=base64.b64encode(raw).decode(),
                        encrypted=True,
                    )
                    msg.id = row["message_id"]
                    msg.sent = row["created_at"]

                    await self.send_to_peer(to_id, msg.to_bytes())
                    logger.info(
                        f"[Resend] Re-sent message {row['message_id']} "
                        f"to {to_id} "
                        f"(attempt {row['retry_count'] + 1})",
                    )
        except asyncio.CancelledError:
            logger.debug("[Resend] _resend_undelivered_loop cancelled")

    async def _resend_file_chunks_loop(self) -> None:
        """Periodically resend undelivered file chunks."""
        try:
            while True:
                await asyncio.sleep(self.resend_interval)
                if not self.peer_id:
                    continue

                cleanup_expired_transfers(
                    ttl=Settings.MESSAGE_TTL,
                    max_retries=Settings.MESSAGE_MAX_RETRIES,
                )

                chunks = get_undelivered_chunks()
                if not chunks:
                    continue

                logger.info(
                    f"[Resend] {len(chunks)} undelivered file chunk(s) found",
                )

                file_cache: dict[str, bytes] = {}
                for ch in chunks:
                    to_id = ch["to_peer_id"]
                    fid = ch["file_id"]
                    increment_chunk_retry(fid, ch["chunk_index"])

                    if routing.get_route(to_id) is None:
                        continue
                    if to_id not in crypto.peers:
                        continue

                    if fid not in file_cache:
                        original = Path(Settings.FILES_DIR) / fid / "original"
                        if not original.exists():
                            continue
                        file_cache[fid] = original.read_bytes()

                    chunk_size = Settings.FILE_CHUNK_SIZE
                    offset = ch["chunk_index"] * chunk_size
                    chunk_data = file_cache[fid][offset : offset + chunk_size]

                    try:
                        raw = await crypto.encrypt_message_to(
                            chunk_data,
                            to_id,
                        )
                    except Exception:  # noqa: BLE001
                        logger.warning(
                            f"[Resend] Encrypt failed for chunk "
                            f"{ch['chunk_index']} of {fid}",
                        )
                        continue

                    fc = FileChunk(
                        from_=self.peer_id,
                        to=to_id,
                        file_id=fid,
                        filename=ch["filename"],
                        chunk_index=ch["chunk_index"],
                        total_chunks=ch["total_chunks"],
                        file_size=ch["file_size"],
                        sha256=ch["sha256"],
                        payload=base64.b64encode(raw).decode(),
                        encrypted=True,
                    )
                    await self.send_to_peer(to_id, fc.to_bytes())
                    logger.info(
                        f"[Resend] File chunk "
                        f"{ch['chunk_index']}/{ch['total_chunks'] - 1} "
                        f"of {fid} re-sent "
                        f"(attempt {ch['retry_count'] + 1})",
                    )
        except asyncio.CancelledError:
            logger.debug(
                "[Resend] _resend_file_chunks_loop cancelled",
            )

    async def send(self, addr: tuple, data: str | bytes, peer_id: str) -> None:
        """Отправить данные ноде. Соединение создаётся по требованию."""
        if isinstance(data, str):
            data = data.encode()
        if not data.endswith(b"\n"):
            data += b"\n"

        last_err: OSError | None = None
        for attempt in range(1, self.send_retries + 1):
            try:
                writer = self._clients.get(addr)
                if writer is None or writer.is_closing():
                    writer = await self._connect(addr)
                if writer is None:
                    msg = f"Cannot connect to {addr}"
                    raise OSError(msg)  # noqa: TRY301
                self._peer_ids[addr] = peer_id
                writer.write(data)
                await writer.drain()
                self._last_active[addr] = asyncio.get_event_loop().time()
            except OSError as e:
                last_err = e
                # Drop broken connection so next attempt reconnects
                old = self._clients.pop(addr, None)
                if old and not old.is_closing():
                    old.close()
                if attempt < self.send_retries:
                    logger.warning(
                        f"[TCP] Send to {addr} failed "
                        f"(attempt {attempt}/{self.send_retries}): {e}. "
                        f"Retrying in {self.retry_delay}s...",
                    )
                    await asyncio.sleep(self.retry_delay)
            else:
                return

        logger.error(
            f"[TCP] Send to {addr} failed after "
            f"{self.send_retries} attempts: {last_err}",
        )

    async def send_to_peer(self, peer_id: str, data: str | bytes) -> None:
        """Отправить данные пиру через таблицу маршрутизации."""
        addr = routing.get_next_hop_addr(peer_id)
        if addr is None:
            logger.warning(f"[TCP] Нет маршрута до {peer_id}")
            return
        route = routing.get_route(peer_id)
        gateway_id = route.gateway if route else peer_id
        await self.send(addr=addr, data=data, peer_id=gateway_id)

    def register_peer_addr(self, addr: tuple, peer_id: str) -> None:
        """Связать TCP-адрес с peer_id.

        Используется при получении PEER_INFO, чтобы при разрыве
        соединения можно было удалить маршруты через этого пира.
        """
        self._peer_ids[addr] = peer_id

    async def _read_loop(
        self,
        reader: asyncio.StreamReader,
        addr: tuple,
    ) -> None:
        """Читает данные из TCP-потока, парсит JSON-сообщения и обрабатывает."""
        recv_buf = b""
        while True:
            try:
                data = await asyncio.wait_for(
                    reader.read(65536),
                    timeout=self.idle_timeout,
                )
            except TimeoutError:
                logger.info(
                    f"[TCP] [{addr}] Read timeout "
                    f"({self.idle_timeout}s), disconnecting",
                )
                break
            if not data:
                break

            self._last_active[addr] = asyncio.get_event_loop().time()
            recv_buf += data

            while b"\n" in recv_buf:
                line, recv_buf = recv_buf.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    message = json.loads(line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    logger.warning(f"[TCP] [{addr}] Invalid data")
                    continue

                logger.debug(f"[TCP] [{addr}] >> {message}")
                await _handle_message(self, message, addr=addr)

    async def handle_request(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        addr: tuple[Any, ...] = writer.get_extra_info("peername")
        sock = writer.get_extra_info("socket")
        if sock is not None:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._clients[addr] = writer
        self._last_active[addr] = asyncio.get_event_loop().time()
        logger.info(f"[TCP] [+] Connected: {addr}")

        try:
            await self._read_loop(reader, addr)
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
            try:
                await writer.wait_closed()
            except (ConnectionResetError, ConnectionAbortedError, OSError):
                pass
