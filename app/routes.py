import asyncio
import time
from pathlib import Path

from fastapi import WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles


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
