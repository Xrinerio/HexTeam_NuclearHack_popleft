from __future__ import annotations

from app.core import utils
from app.database import database


def create_file_transfer(
    *,
    file_id: str,
    from_peer_id: str,
    to_peer_id: str,
    filename: str,
    file_size: int,
    sha256: str,
    total_chunks: int,
    is_outgoing: bool,
) -> dict:
    created_at = utils.now()
    database.execute(
        "INSERT OR IGNORE INTO file_transfers "
        "(file_id, from_peer_id, to_peer_id, filename, file_size, sha256, "
        "total_chunks, received_chunks, is_outgoing, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, 'pending', ?)",
        (
            file_id,
            from_peer_id,
            to_peer_id,
            filename,
            file_size,
            sha256,
            total_chunks,
            int(is_outgoing),
            created_at,
        ),
    )
    return {
        "file_id": file_id,
        "from_peer_id": from_peer_id,
        "to_peer_id": to_peer_id,
        "filename": filename,
        "file_size": file_size,
        "sha256": sha256,
        "total_chunks": total_chunks,
        "received_chunks": 0,
        "is_outgoing": is_outgoing,
        "status": "pending",
        "created_at": created_at,
    }


def create_outgoing_chunks(file_id: str, total_chunks: int) -> None:
    params = [(file_id, i) for i in range(total_chunks)]
    database.execute_many(
        "INSERT OR IGNORE INTO file_chunks "
        "(file_id, chunk_index) VALUES (?, ?)",
        params,
    )


def mark_chunk_delivered(file_id: str, chunk_index: int) -> bool:
    row = database.fetch_one(
        "SELECT id, delivered FROM file_chunks "
        "WHERE file_id = ? AND chunk_index = ?",
        (file_id, chunk_index),
    )
    if row is None:
        return False
    if row["delivered"]:
        return True
    database.execute(
        "UPDATE file_chunks SET delivered = 1 "
        "WHERE file_id = ? AND chunk_index = ?",
        (file_id, chunk_index),
    )
    undelivered = database.fetch_one(
        "SELECT COUNT(*) AS cnt FROM file_chunks "
        "WHERE file_id = ? AND delivered = 0",
        (file_id,),
    )
    if undelivered and undelivered["cnt"] == 0:
        database.execute(
            "UPDATE file_transfers SET status = 'completed' WHERE file_id = ?",
            (file_id,),
        )
    return True


def increment_received_chunks(file_id: str) -> int:
    database.execute(
        "UPDATE file_transfers SET received_chunks = received_chunks + 1, "
        "status = 'in_progress' WHERE file_id = ?",
        (file_id,),
    )
    row = database.fetch_one(
        "SELECT received_chunks FROM file_transfers WHERE file_id = ?",
        (file_id,),
    )
    return row["received_chunks"] if row else 0


def complete_file_transfer(file_id: str) -> None:
    database.execute(
        "UPDATE file_transfers SET status = 'completed' WHERE file_id = ?",
        (file_id,),
    )


def fail_file_transfer(file_id: str) -> None:
    database.execute(
        "UPDATE file_transfers SET status = 'failed' WHERE file_id = ?",
        (file_id,),
    )


def get_file_transfer(file_id: str) -> dict | None:
    row = database.fetch_one(
        "SELECT * FROM file_transfers WHERE file_id = ?",
        (file_id,),
    )
    if row is None:
        return None
    return _row_to_dict(row)


def get_all_file_transfers() -> list[dict]:
    rows = database.fetch_all(
        "SELECT * FROM file_transfers ORDER BY created_at DESC",
    )
    return [_row_to_dict(r) for r in rows]


def get_undelivered_chunks() -> list[dict]:
    rows = database.fetch_all(
        "SELECT fc.file_id, fc.chunk_index, fc.retry_count, "
        "ft.to_peer_id, ft.filename, ft.total_chunks, "
        "ft.file_size, ft.sha256 "
        "FROM file_chunks fc "
        "JOIN file_transfers ft ON fc.file_id = ft.file_id "
        "WHERE fc.delivered = 0 AND ft.is_outgoing = 1 "
        "AND ft.status NOT IN ('completed', 'failed') "
        "ORDER BY fc.file_id, fc.chunk_index",
    )
    return [
        {
            "file_id": r["file_id"],
            "chunk_index": r["chunk_index"],
            "retry_count": r["retry_count"],
            "to_peer_id": r["to_peer_id"],
            "filename": r["filename"],
            "total_chunks": r["total_chunks"],
            "file_size": r["file_size"],
            "sha256": r["sha256"],
        }
        for r in rows
    ]


def increment_chunk_retry(file_id: str, chunk_index: int) -> None:
    database.execute(
        "UPDATE file_chunks SET retry_count = retry_count + 1 "
        "WHERE file_id = ? AND chunk_index = ?",
        (file_id, chunk_index),
    )


def cleanup_expired_transfers(*, ttl: int, max_retries: int) -> int:
    cutoff = utils.now() - ttl
    expired = database.fetch_all(
        "SELECT file_id FROM file_transfers "
        "WHERE status NOT IN ('completed', 'failed') "
        "AND created_at < ?",
        (cutoff,),
    )
    for r in expired:
        fid = r["file_id"]
        database.execute(
            "DELETE FROM file_chunks WHERE file_id = ?",
            (fid,),
        )
        database.execute(
            "UPDATE file_transfers SET status = 'failed' WHERE file_id = ?",
            (fid,),
        )
    exhausted = database.fetch_all(
        "SELECT DISTINCT fc.file_id FROM file_chunks fc "
        "JOIN file_transfers ft ON fc.file_id = ft.file_id "
        "WHERE fc.retry_count >= ? AND fc.delivered = 0 "
        "AND ft.status NOT IN ('completed', 'failed')",
        (max_retries,),
    )
    for r in exhausted:
        database.execute(
            "UPDATE file_transfers SET status = 'failed' WHERE file_id = ?",
            (r["file_id"],),
        )
    return len(expired) + len(exhausted)


def _row_to_dict(r: object) -> dict:
    return {
        "file_id": r["file_id"],
        "from_peer_id": r["from_peer_id"],
        "to_peer_id": r["to_peer_id"],
        "filename": r["filename"],
        "file_size": r["file_size"],
        "sha256": r["sha256"],
        "total_chunks": r["total_chunks"],
        "received_chunks": r["received_chunks"],
        "is_outgoing": bool(r["is_outgoing"]),
        "status": r["status"],
        "created_at": r["created_at"],
    }
