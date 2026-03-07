import base64

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.core import logger
from app.crypto.crypto import crypto
from app.network import routing
from app.protocol import Message

router: APIRouter = APIRouter()


class SendMessageRequest(BaseModel):
    to: str
    payload: str


@router.get("/peers")
async def get_peers() -> list[dict]:
    return routing.get_advertisement(to_node_id="")


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
        raise HTTPException(
            status_code=503,
            detail=f"No encryption key for peer {body.to!r}. Key exchange in progress.",
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
    return {"id": msg.id, "to": body.to, "encrypted": True}
