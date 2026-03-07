from __future__ import annotations

import base64
import hashlib
import math
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from app.core import Settings, logger
from app.crud.file_transfers import (
    create_file_transfer,
    create_outgoing_chunks,
    get_all_file_transfers,
    get_file_transfer,
)
from app.crypto.crypto import crypto
from app.network import routing
from app.network.ws_manager import ws_manager
from app.protocol import FileChunk, KeyExchange

router: APIRouter = APIRouter()


@router.post("/files/send")
async def send_file(
    request: Request,
    peer_id: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
) -> dict:
    """Upload and send a file to a peer."""
    server = request.app.state.server

    content = await file.read()
    filename = file.filename or "unnamed"
    file_size = len(content)
    sha256_hash = hashlib.sha256(content).hexdigest()
    file_id = str(uuid.uuid4())

    chunk_size = Settings.FILE_CHUNK_SIZE
    total_chunks = max(1, math.ceil(file_size / chunk_size))

    # Save original file to disk
    transfer_dir = Path(Settings.FILES_DIR) / file_id
    transfer_dir.mkdir(parents=True, exist_ok=True)
    (transfer_dir / "original").write_bytes(content)

    # Save metadata to DB
    transfer = create_file_transfer(
        file_id=file_id,
        from_peer_id=server.peer_id,
        to_peer_id=peer_id,
        filename=filename,
        file_size=file_size,
        sha256=sha256_hash,
        total_chunks=total_chunks,
        is_outgoing=True,
    )
    create_outgoing_chunks(file_id, total_chunks)

    # Try to send chunks immediately
    if peer_id in crypto.peers and routing.get_route(peer_id) is not None:
        for i in range(total_chunks):
            offset = i * chunk_size
            chunk_data = content[offset : offset + chunk_size]
            raw = await crypto.encrypt_message_to(chunk_data, peer_id)
            chunk = FileChunk(
                from_=server.peer_id,
                to=peer_id,
                file_id=file_id,
                filename=filename,
                chunk_index=i,
                total_chunks=total_chunks,
                file_size=file_size,
                sha256=sha256_hash,
                payload=base64.b64encode(raw).decode(),
                encrypted=True,
            )
            await server.send_to_peer(peer_id, chunk.to_bytes())
        logger.info(
            f"[API] File {file_id} ({filename}) "
            f"sent {total_chunks} chunk(s) to {peer_id}",
        )
    else:
        # Initiate key exchange if needed
        if (
            routing.get_route(peer_id) is not None
            and peer_id not in crypto.peers
            and server.peer_id
            and crypto.public_key is not None
        ):
            kex = KeyExchange(
                from_=server.peer_id,
                to=peer_id,
                public_key=base64.b64encode(
                    bytes(crypto.public_key),
                ).decode(),
            )
            await server.send_to_peer(peer_id, kex.to_bytes())
        logger.info(
            f"[API] File {file_id} queued for delivery to {peer_id}",
        )

    await ws_manager.broadcast("file_transfer_started", transfer)
    return transfer


@router.get("/files")
async def list_file_transfers() -> list[dict]:
    """List all file transfers."""
    return get_all_file_transfers()


@router.get("/files/{file_id}")
async def get_transfer_status(file_id: str) -> dict:
    """Get status of a file transfer."""
    transfer = get_file_transfer(file_id)
    if transfer is None:
        raise HTTPException(status_code=404, detail="Transfer not found")
    return transfer


@router.get("/files/{file_id}/download")
async def download_file(file_id: str) -> FileResponse:
    """Download a completed file."""
    transfer = get_file_transfer(file_id)
    if transfer is None:
        raise HTTPException(status_code=404, detail="Transfer not found")
    if transfer["status"] != "completed":
        raise HTTPException(
            status_code=409,
            detail="Transfer not yet completed",
        )

    transfer_dir = Path(Settings.FILES_DIR) / file_id
    file_path = (
        transfer_dir / "original"
        if transfer["is_outgoing"]
        else transfer_dir / "complete"
    )

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail="File not found on disk",
        )

    return FileResponse(
        path=str(file_path),
        filename=transfer["filename"],
        media_type="application/octet-stream",
    )
