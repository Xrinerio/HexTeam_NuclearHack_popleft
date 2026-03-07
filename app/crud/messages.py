from __future__ import annotations

from app.database import database


def save_message(
    *,
    message_id: str,
    from_peer_id: str,
    to_peer_id: str,
    content: str,
    is_outgoing: bool,
    created_at: int,
) -> dict:
    database.execute(
        "INSERT OR IGNORE INTO messages "
        "(message_id, from_peer_id, to_peer_id, content, is_outgoing, delivered, created_at) "
        "VALUES (?, ?, ?, ?, ?, 0, ?)",
        (
            message_id,
            from_peer_id,
            to_peer_id,
            content,
            int(is_outgoing),
            created_at,
        ),
    )
    return {
        "message_id": message_id,
        "from_peer_id": from_peer_id,
        "to_peer_id": to_peer_id,
        "content": content,
        "is_outgoing": is_outgoing,
        "delivered": False,
        "timestamp": created_at,
    }


def mark_delivered(message_id: str) -> bool:
    row = database.fetch_one(
        "SELECT id FROM messages WHERE message_id = ?",
        (message_id,),
    )
    if row is None:
        return False
    database.execute(
        "UPDATE messages SET delivered = 1 WHERE message_id = ?",
        (message_id,),
    )
    return True


def get_chat_messages(peer_id: str) -> list[dict]:
    rows = database.fetch_all(
        "SELECT message_id, from_peer_id, to_peer_id, content, is_outgoing, delivered, created_at "
        "FROM messages "
        "WHERE from_peer_id = ? OR to_peer_id = ? "
        "ORDER BY created_at ASC",
        (peer_id, peer_id),
    )
    return [
        {
            "message_id": r["message_id"],
            "from_peer_id": r["from_peer_id"],
            "to_peer_id": r["to_peer_id"],
            "content": r["content"],
            "is_outgoing": bool(r["is_outgoing"]),
            "delivered": bool(r["delivered"]),
            "timestamp": r["created_at"],
        }
        for r in rows
    ]
