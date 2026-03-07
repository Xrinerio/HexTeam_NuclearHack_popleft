from fastapi import APIRouter

from . import auth, files, peer, ping

api: APIRouter = APIRouter(prefix="/api")

api.include_router(auth.router, tags=["Auth"])
api.include_router(peer.router, tags=["Peer"])
api.include_router(files.router, tags=["Files"])
api.include_router(ping.router, tags=["Ping"])

__all__ = ["api"]
