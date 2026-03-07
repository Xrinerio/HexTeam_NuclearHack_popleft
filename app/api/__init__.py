from fastapi import APIRouter

from . import auth, files, peer

api: APIRouter = APIRouter(prefix="/api")

api.include_router(auth.router, tags=["Auth"])
api.include_router(peer.router, tags=["Peer"])
api.include_router(files.router, tags=["Files"])

__all__ = ["api"]
