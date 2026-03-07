import asyncio
import json
from typing import Any

from fastapi import WebSocket

from app.core import logger


class WebSocketManager:
    def __init__(self) -> None:
        self._connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections.append(ws)
        logger.info(f"[WS] Client connected (total: {len(self._connections)})")

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            if ws in self._connections:
                self._connections.remove(ws)
        logger.info(
            f"[WS] Client disconnected (total: {len(self._connections)})"
        )

    async def broadcast(self, event: str, data: dict[str, Any]) -> None:
        payload = json.dumps({"event": event, "data": data})
        async with self._lock:
            dead: list[WebSocket] = []
            for ws in self._connections:
                try:
                    await ws.send_text(payload)
                except Exception:  # noqa: BLE001
                    dead.append(ws)
            for ws in dead:
                self._connections.remove(ws)


ws_manager = WebSocketManager()
