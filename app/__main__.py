from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import api
from app.core import Settings
from app.crud.users import get_current_user
from app.crypto.crypto import crypto
from app.database import database
from app.server import Server

# Инициализируем таблицы и загружаем identity до создания сервера
database.initialize_tables()
_user = get_current_user()
if _user is not None:
    Settings.PEER_ID = _user["peer_id"]
    Settings.USERNAME = _user["username"]

server: Server = Server(
    host=Settings.HOST,
    port=Settings.PORT,
    peer_id=Settings.PEER_ID or "",
    discovery_interval=Settings.DISCOVERY_INTERVAL,
    discovery_port=Settings.DISCOVERY_PORT,
    idle_timeout=Settings.IDLE_TIMEOUT,
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await crypto.initialize()
    await server.start_server()
    app.state.server = server
    yield
    await server.stop_server()
    await crypto.write_peers()


app: FastAPI = FastAPI(title="P2P Chat", lifespan=lifespan)
app.include_router(api)
app.mount(
    "/",
    StaticFiles(directory=Path(__file__).parent / "static", html=True),
)

if __name__ == "__main__":
    uvicorn.run(
        app,
        host=Settings.UVICORN_HOST,
        port=Settings.UVICORN_PORT,
        reload=False,
        log_level=20,
    )
