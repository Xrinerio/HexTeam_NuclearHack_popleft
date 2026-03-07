from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import api
from app.core import Settings
from app.crypto.crypto import crypto
from app.database import database
from app.server import Server

server: Server = Server(
    host=Settings.HOST,
    port=Settings.PORT,
    peer_id=Settings.PEER_ID,
    discovery_interval=Settings.DISCOVERY_INTERVAL,
    discovery_port=Settings.DISCOVERY_PORT,
    idle_timeout=Settings.IDLE_TIMEOUT,
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await crypto.initialize()
    database.initialize_tables()
    await server.start_server()
    app.state.server = server
    yield
    await server.stop_server()
    await crypto.write_peers()


app: FastAPI = FastAPI(title="P2P Chat", lifespan=lifespan)
app.mount(
    "/",
    StaticFiles(directory=Path(__file__).parent / "static", html=True),
)
app.include_router(api)

if __name__ == "__main__":
    uvicorn.run(
        app,
        host=Settings.UVICORN_HOST,
        port=Settings.UVICORN_PORT,
        reload=False,
        log_level=20,
    )
