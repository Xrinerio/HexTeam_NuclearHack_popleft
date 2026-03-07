import base64
import json

from fastapi import (
    APIRouter,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel

from app.core import logger
from app.crud.messages import get_chat_messages, get_chat_peer_ids, save_message
from app.crypto.crypto import crypto
from app.network import routing
from app.network.ws_manager import ws_manager
from app.protocol import CallAudio, KeyExchange, Message

router: APIRouter = APIRouter()


class SendMessageRequest(BaseModel):
    to: str
    payload: str


class ChatMessageRequest(BaseModel):
    peer_id: str
    content: str


@router.get("/peers")
async def get_peers() -> list[dict]:
    """Получить список доступных пиров."""
    routes = routing.get_advertisement(to_node_id="")
    logger.info(routing)
    # Преобразуем данные маршрутизации в формат для фронтенда
    peers_list = []
    for route_info in routes:
        destination = route_info.get("destination")
        if not isinstance(destination, str):
            continue
        route = routing.get_route(destination)
        if route:
            peers_list.append(
                {
                    "node_id": route.destination,
                    "name": route.name,
                    "ip": route.ip or "unknown",
                    "port": route.port,
                    "hops": route.hops,
                },
            )
    return peers_list


@router.post("/send")
async def send_message(body: SendMessageRequest, request: Request) -> dict:
    server = request.app.state.server

    msg = Message(
        from_=server.peer_id,
        to=body.to,
        payload=body.payload,
        encrypted=False,
    )

    # Try to encrypt and send immediately if possible
    sent = False
    if body.to in crypto.peers and routing.get_route(body.to) is not None:
        raw = await crypto.encrypt_message_to(body.payload.encode(), body.to)
        msg.payload = base64.b64encode(raw).decode()
        msg.encrypted = True
        await server.send_to_peer(body.to, msg.to_bytes())
        sent = True
        logger.info(f"[API] MESSAGE sent: id={msg.id} to={body.to}")
    else:
        # Initiate key exchange if we have a route but no key
        if (
            routing.get_route(body.to) is not None
            and body.to not in crypto.peers
            and server.peer_id
            and crypto.public_key is not None
        ):
            kex = KeyExchange(
                from_=server.peer_id,
                to=body.to,
                public_key=base64.b64encode(
                    bytes(crypto.public_key),
                ).decode(),
            )
            await server.send_to_peer(body.to, kex.to_bytes())
            logger.info(f"[API] KEY_EXCHANGE initiated to {body.to}")
        logger.info(
            f"[API] MESSAGE queued for later delivery: "
            f"id={msg.id} to={body.to}",
        )

    saved = save_message(
        message_id=msg.id,
        from_peer_id=server.peer_id,
        to_peer_id=body.to,
        content=body.payload,
        is_outgoing=True,
        created_at=msg.sent,
    )
    await ws_manager.broadcast("new_message", saved)

    return {
        "id": msg.id,
        "to": body.to,
        "encrypted": msg.encrypted,
        "sent": sent,
    }


@router.post("/messages")
async def send_chat_message(body: ChatMessageRequest, request: Request) -> dict:
    server = request.app.state.server
    peer_id = body.peer_id
    content = body.content

    msg = Message(
        from_=server.peer_id,
        to=peer_id,
        payload=content,
        encrypted=False,
    )

    # Try to encrypt and send immediately if possible
    if peer_id in crypto.peers and routing.get_route(peer_id) is not None:
        raw = await crypto.encrypt_message_to(content.encode(), peer_id)
        payload_b64 = base64.b64encode(raw).decode()
        msg.payload = payload_b64
        msg.encrypted = True
        await server.send_to_peer(peer_id, msg.to_bytes())
        logger.info(f"[API] Chat message sent: id={msg.id} to={peer_id}")
    else:
        # Initiate key exchange if we have a route but no key
        if (
            routing.get_route(peer_id) is not None
            and peer_id not in crypto.peers
            and server.peer_id
            and crypto.public_key is not None
        ):
            kex = KeyExchange(
                from_=server.peer_id,
                to=peer_id,
                public_key=base64.b64encode(
                    bytes(crypto.public_key),
                ).decode(),
            )
            await server.send_to_peer(peer_id, kex.to_bytes())
            logger.info(f"[API] KEY_EXCHANGE initiated to {peer_id}")
        logger.info(
            f"[API] Chat message queued for later delivery: "
            f"id={msg.id} to={peer_id}",
        )

    saved = save_message(
        message_id=msg.id,
        from_peer_id=server.peer_id,
        to_peer_id=peer_id,
        content=content,
        is_outgoing=True,
        created_at=msg.sent,
    )
    await ws_manager.broadcast("new_message", saved)
    return saved


@router.get("/messages/{peer_id}")
async def get_messages(peer_id: str) -> list[dict]:
    return get_chat_messages(peer_id)


@router.get("/chats")
async def get_chats() -> list[dict]:
    """Return peer_ids with names that have message history."""
    return get_chat_peer_ids()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws_manager.connect(ws)
    try:
        while True:
            text = await ws.receive_text()
            try:
                msg = json.loads(text)
                if msg.get("event") == "call_audio":
                    await _relay_call_audio(ws, msg.get("data", {}))
            except (json.JSONDecodeError, KeyError):
                pass
    except WebSocketDisconnect:
        pass
    finally:
        await ws_manager.disconnect(ws)


async def _relay_call_audio(ws: WebSocket, data: dict) -> None:
    """Encrypt browser audio and send to peer via TCP."""
    server = ws.app.state.server
    peer_id = data.get("peer_id", "")
    call_id = data.get("call_id", "")
    audio_b64 = data.get("audio", "")

    if not peer_id or not call_id or not audio_b64:
        return
    if call_id not in server.active_calls:
        return
    if peer_id not in crypto.peers:
        return

    try:
        audio_bytes = base64.b64decode(audio_b64)
        encrypted = await crypto.encrypt_message_to(audio_bytes, peer_id)
        payload_b64 = base64.b64encode(encrypted).decode()
    except Exception:  # noqa: BLE001
        return

    pkt = CallAudio(
        from_=server.peer_id,
        to=peer_id,
        call_id=call_id,
        seq=data.get("seq", 0),
        payload=payload_b64,
    )
    await server.send_to_peer(peer_id, pkt.to_bytes())
