import argparse
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from app.discovery import Discovery
from app.server import TCPServer
from app.settings import Settings

parser = argparse.ArgumentParser(description="LAN Peer Discovery")
parser.add_argument(
    "--port",
    "-p",
    type=int,
    default=8000,
    help="HTTP server port",
)
args, _ = parser.parse_known_args()


settings = Settings()
discovery = Discovery(http_port=args.port)
tcp_server = TCPServer(host=settings.HOST, port=settings.PORT)

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await discovery.start()
    await tcp_server.start_server()
    yield
    await tcp_server.stop_server()
    await discovery.stop()


app = FastAPI(title="LAN Peer Discovery", lifespan=lifespan)

if __name__ == "__main__":
    uvicorn.run(app, host=settings.HOST, port=args.port, reload=False)
