from fastapi import APIRouter

from . import auth, peer

api: APIRouter = APIRouter(prefix="/api")

api.include_router(auth.router, tags=["Auth"])
api.include_router(peer.router, tags=["Peer"])

__all__ = ["api"]
