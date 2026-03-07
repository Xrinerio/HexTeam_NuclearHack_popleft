from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.core import logger, utils
from app.protocol import Ping

router: APIRouter = APIRouter()

PING_TIMEOUT = 10.0


class PingRequest(BaseModel):
    peer_id: str


@router.post("/ping")
async def ping_peer(request: Request, body: PingRequest) -> dict:
    """Send a ping to a peer and measure round-trip time."""
    server = request.app.state.server
    peer_id = body.peer_id

    if not server.peer_id:
        raise HTTPException(status_code=503, detail="Server not ready")

    ping_id = str(uuid.uuid4())
    send_ts = utils.now_ms()

    ping = Ping(
        from_=server.peer_id,
        to=peer_id,
        ping_id=ping_id,
        timestamp=send_ts,
    )

    loop = asyncio.get_running_loop()
    future: asyncio.Future = loop.create_future()
    server.pending_pings[ping_id] = future

    await server.send_to_peer(peer_id, ping.to_bytes())
    logger.info(f"[PING] Sent ping {ping_id} to {peer_id}")

    try:
        pong = await asyncio.wait_for(future, timeout=PING_TIMEOUT)
    except TimeoutError:
        server.pending_pings.pop(ping_id, None)
        raise HTTPException(
            status_code=504,
            detail="Ping timed out",
        ) from None

    receive_ts = utils.now_ms()

    rtt = receive_ts - send_ts
    time_to_target = pong["pong_timestamp"] - pong["ping_timestamp"]
    time_from_target = receive_ts - pong["pong_timestamp"]

    return {
        "peer_id": peer_id,
        "ping_id": ping_id,
        "rtt_ms": round(rtt, 2),
        "time_to_target_ms": round(time_to_target, 2),
        "time_from_target_ms": round(time_from_target, 2),
    }
