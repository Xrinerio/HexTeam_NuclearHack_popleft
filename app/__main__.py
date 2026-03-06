import argparse
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from app.database import database
from app.server import TCPServer
from app.settings import settings

parser = argparse.ArgumentParser(description="LAN Peer Discovery")
parser.add_argument(
    "--port",
    "-p",
    type=int,
    default=settings.PORT,
    help="HTTP server port",
)
args, _ = parser.parse_known_args()


tcp_server = TCPServer(
    host=settings.HOST,
    port=args.port,
    node_id=settings.NODE_ID,
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
    uvicorn.run(app, host=settings.HOST, port=args.port, reload=False)
