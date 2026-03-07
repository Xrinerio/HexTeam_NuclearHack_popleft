from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.core import logger, utils
from app.network.routing import routing
from app.protocol import CallAnswer, CallEnd, CallOffer

router: APIRouter = APIRouter()


class CallOfferRequest(BaseModel):
    peer_id: str


class CallAnswerRequest(BaseModel):
    call_id: str
    accepted: bool


class CallEndRequest(BaseModel):
    call_id: str


@router.post("/call/offer")
async def offer_call(request: Request, body: CallOfferRequest) -> dict:
    server = request.app.state.server

    if not server.peer_id:
        raise HTTPException(status_code=503, detail="Server not ready")

    if routing.get_next_hop_addr(body.peer_id) is None:
        raise HTTPException(
            status_code=404,
            detail="Peer is not reachable",
        )

    call_id = str(uuid.uuid4())
    offer = CallOffer(
        from_=server.peer_id,
        to=body.peer_id,
        call_id=call_id,
    )
    server.active_calls[call_id] = {
        "peer_a": server.peer_id,
        "peer_b": body.peer_id,
        "started_at": utils.now(),
    }
    await server.send_to_peer(body.peer_id, offer.to_bytes())
    logger.info(f"[CALL] Offer {call_id} sent to {body.peer_id}")
    return {"call_id": call_id, "peer_id": body.peer_id}


@router.post("/call/answer")
async def answer_call(request: Request, body: CallAnswerRequest) -> dict:
    server = request.app.state.server
    call = server.active_calls.get(body.call_id)
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    other = (
        call["peer_a"] if call["peer_b"] == server.peer_id else call["peer_b"]
    )
    answer = CallAnswer(
        from_=server.peer_id,
        to=other,
        call_id=body.call_id,
        accepted=body.accepted,
    )
    await server.send_to_peer(other, answer.to_bytes())

    if not body.accepted:
        server.active_calls.pop(body.call_id, None)

    logger.info(
        f"[CALL] Answer {body.call_id}: "
        f"{'accepted' if body.accepted else 'rejected'}",
    )
    return {"call_id": body.call_id, "accepted": body.accepted}


@router.post("/call/end")
async def end_call(request: Request, body: CallEndRequest) -> dict:
    server = request.app.state.server
    call = server.active_calls.pop(body.call_id, None)
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    other = (
        call["peer_a"] if call["peer_b"] == server.peer_id else call["peer_b"]
    )
    end = CallEnd(
        from_=server.peer_id,
        to=other,
        call_id=body.call_id,
    )
    await server.send_to_peer(other, end.to_bytes())
    logger.info(f"[CALL] Ended {body.call_id}")
    return {"call_id": body.call_id}
