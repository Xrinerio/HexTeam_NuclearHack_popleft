import base64

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core import logger
from app.crypto.crypto import crypto
from app.network import routing
from app.protocol import KeyExchange, Message

router: APIRouter = APIRouter()


class SendMessageRequest(BaseModel):
    to: str
    payload: str


@router.get("/peers")
async def get_peers() -> list[dict]:
    """Получить список доступных пиров."""
    routes = routing.get_advertisement(to_node_id="")
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
                }
            )
    return peers_list


@router.post("/send")
async def send_message(body: SendMessageRequest, request: Request) -> dict:
    server = request.app.state.server

    if routing.get_route(body.to) is None:
        raise HTTPException(
            status_code=404,
            detail=f"No route to peer {body.to!r}",
        )

    payload = body.payload
    if body.to not in crypto.peers:
        if (
            routing.get_route(body.to) is not None
            and server.peer_id
            and crypto.public_key is not None
        ):
            kex = KeyExchange(
                from_=server.peer_id,
                to=body.to,
                public_key=base64.b64encode(bytes(crypto.public_key)).decode(),  # type: ignore[arg-type]
            )
            await server.send_to_peer(body.to, kex.to_bytes())
            logger.info(f"[API] KEY_EXCHANGE initiated to {body.to}")
        return JSONResponse(
            status_code=202,
            content={
                "detail": (
                    f"No encryption key for peer {body.to!r}."
                    " Key exchange initiated, retry shortly."
                ),
            },
        )

    raw = await crypto.encrypt_message_to(payload.encode(), body.to)
    payload = base64.b64encode(raw).decode()
    logger.info(f"[API] Sending encrypted MESSAGE to {body.to}")

    msg = Message(
        from_=server.peer_id,
        to=body.to,
        payload=payload,
        encrypted=True,
    )
    await server.send_to_peer(body.to, msg.to_bytes())
    logger.info(f"[API] MESSAGE sent: id={msg.id} to={body.to}")
    return {"id": msg.id, "to": body.to, "encrypted": True}
