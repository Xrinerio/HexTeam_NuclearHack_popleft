import sqlite3

from app.database import database


def create_user(peer_id: str, username: str) -> sqlite3.Row:
    database.execute(
        "INSERT INTO users (peer_id, username) VALUES (?, ?)",
        (peer_id, username),
    )
    row = database.fetch_one(
        "SELECT peer_id, username, created_at FROM users WHERE peer_id = ?",
        (peer_id,),
    )
    if row is None:
        msg = "Failed to create user"
        raise RuntimeError(msg)
    return row


def get_user(peer_id: str) -> sqlite3.Row | None:
    return database.fetch_one(
        "SELECT peer_id, username, created_at FROM users WHERE peer_id = ?",
        (peer_id,),
    )


def username_exists(username: str) -> bool:
    return (
        database.fetch_one(
            "SELECT 1 FROM users WHERE username = ?",
            (username,),
        )
        is not None
    )


def get_current_user() -> sqlite3.Row | None:
    """Возвращает единственного локально зарегистрированного пользователя."""
    return database.fetch_one(
        "SELECT peer_id, username, created_at FROM users LIMIT 1",
    )
