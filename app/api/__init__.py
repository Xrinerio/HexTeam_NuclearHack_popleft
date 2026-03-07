from fastapi import APIRouter

from . import auth, call, files, peer, ping

api: APIRouter = APIRouter(prefix="/api")

api.include_router(auth.router, tags=["Auth"])
api.include_router(peer.router, tags=["Peer"])
api.include_router(files.router, tags=["Files"])
api.include_router(ping.router, tags=["Ping"])
api.include_router(call.router, tags=["Call"])

__all__ = ["api"]
