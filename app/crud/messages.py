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


def get_chat_peer_ids() -> list[dict]:
    """Return peer_ids with names that have message history."""
    rows = database.fetch_all(
        "SELECT DISTINCT p.peer_id, COALESCE(u.username, p.peer_id) AS name FROM ("
        "  SELECT from_peer_id AS peer_id FROM messages WHERE is_outgoing = 0 "
        "  UNION "
        "  SELECT to_peer_id AS peer_id FROM messages WHERE is_outgoing = 1"
        ") p LEFT JOIN users u ON u.peer_id = p.peer_id",
    )
    return [{"peer_id": r["peer_id"], "name": r["name"]} for r in rows]


def get_undelivered_outgoing() -> list[dict]:
    """Return outgoing messages that have not been acknowledged yet."""
    rows = database.fetch_all(
        "SELECT message_id, from_peer_id, to_peer_id, content, created_at "
        "FROM messages "
        "WHERE is_outgoing = 1 AND delivered = 0 "
        "ORDER BY created_at ASC",
    )
    return [
        {
            "message_id": r["message_id"],
            "from_peer_id": r["from_peer_id"],
            "to_peer_id": r["to_peer_id"],
            "content": r["content"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]
