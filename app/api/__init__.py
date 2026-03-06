from fastapi import APIRouter

from . import peer

api: APIRouter = APIRouter(prefix="/api")

api.include_router(peer.router, tags=["Peer"])

__all__ = ["api"]
