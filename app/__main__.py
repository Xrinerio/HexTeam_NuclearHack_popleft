from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from app.database import database
from app.server import Server
from app.settings import settings

tcp_server = Server(
    host=settings.HOST,
    port=settings.PORT,
    peer_id=settings.PEER_ID,
    discovery_interval=settings.DISCOVERY_INTERVAL,
    discovery_port=settings.DISCOVERY_PORT,
    idle_timeout=settings.IDLE_TIMEOUT,
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    database.initialize_tables()
    await tcp_server.start_server()
    yield
    await tcp_server.stop_server()


app = FastAPI(title="LAN Peer Discovery", lifespan=lifespan)

if __name__ == "__main__":
    uvicorn.run(
        app, host=settings.HOST,
        port=settings.UVICORN_PORT,
        reload=False,
    )
