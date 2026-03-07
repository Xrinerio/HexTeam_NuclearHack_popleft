CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT NOT NULL UNIQUE,
    from_peer_id TEXT NOT NULL,
    to_peer_id TEXT NOT NULL,
    content TEXT NOT NULL,
    is_outgoing BOOLEAN NOT NULL DEFAULT 0,
    delivered BOOLEAN NOT NULL DEFAULT 0,
    retry_count INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
);


CREATE TABLE IF NOT EXISTS keys (
    peer_id TEXT PRIMARY KEY NOT NULL UNIQUE,
    public_key TEXT NOT NULL
);
