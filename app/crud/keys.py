from app.database import database


def get_all_keys() -> dict[str, str]:
    rows = database.fetch_all("SELECT peer_id, public_key FROM keys")
    return {row["peer_id"]: row["public_key"] for row in rows}


def add_all_keys(keys: dict[str, str]) -> None:
    database.execute_many(
        "INSERT OR REPLACE INTO keys (peer_id, public_key) VALUES (?, ?)",
        list(keys.items()),
    )


def is_peer_verified(peer_id: str) -> bool:
    row = database.fetch_one(
        "SELECT verified FROM keys WHERE peer_id = ?",
        (peer_id,),
    )
    return bool(row and row["verified"])


def set_peer_verified(peer_id: str, *, verified: bool) -> None:
    database.execute(
        "UPDATE keys SET verified = ? WHERE peer_id = ?",
        (int(verified), peer_id),
    )
