from app.database import database


def get_all_keys() -> dict[str, str]:
    rows = database.fetch_all("SELECT peer_id, public_key FROM keys")
    return {row["peer_id"]: row["public_key"] for row in rows}


def add_all_keys(keys: dict[str, str]) -> None:
    database.execute_many(
        "INSERT OR REPLACE INTO keys (peer_id, public_key) VALUES (?, ?)",
        list(keys.items()),
    )
