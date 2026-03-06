import argparse
import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from discovery import Discovery

parser = argparse.ArgumentParser(description="LAN Peer Discovery")
parser.add_argument(
    "--port",
    "-p",
    type=int,
    default=8000,
    help="HTTP server port",
)
args, _ = parser.parse_known_args()

discovery = Discovery(http_port=args.port)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    await discovery.start()
    yield
    await discovery.stop()


app = FastAPI(title="LAN Peer Discovery", lifespan=lifespan)


@app.get("/api/me")  # type: ignore[misc]
async def api_me() -> dict:
    return discovery.get_me()


@app.get("/api/peers")  # type: ignore[misc]
async def api_peers() -> list[dict]:
    return discovery.get_peers_list()


@app.get("/api/status")  # type: ignore[misc]
async def api_status() -> dict:
    return {
        "status": "running",
        "node_id": discovery.node_id,
        "peers_count": len(discovery.peers),
        "uptime": round(time.time() - discovery.start_time, 1),
    }


@app.websocket("/ws")  # type: ignore[misc]
async def ws_peers(ws: WebSocket) -> None:
    await ws.accept()
    try:
        while True:
            await ws.send_json({"peers": discovery.get_peers_list()})
            await asyncio.sleep(1)
    except (WebSocketDisconnect, RuntimeError):
        pass


app.mount(
    "/",
    StaticFiles(directory=Path(__file__).parent / "static", html=True),
)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=args.port)  # noqa: S104
