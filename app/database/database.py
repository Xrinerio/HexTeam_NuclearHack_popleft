import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import cast


class Database:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    def initialize_tables(self) -> None:
        schemas_dir = Path(__file__).parent / "schemas"
        if not schemas_dir.exists():
            return

        for schema_file in sorted(schemas_dir.glob("*.sql")):
            schema = schema_file.read_text(encoding="utf-8")
            self.create_tables(schema)

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def execute(self, query: str, params: tuple = ()) -> None:
        with self.get_connection() as conn:
            conn.execute(query, params)

    def execute_many(self, query: str, params_list: list[tuple]) -> None:
        with self.get_connection() as conn:
            conn.executemany(query, params_list)

    def fetch_one(self, query: str, params: tuple = ()) -> sqlite3.Row | None:
        with self.get_connection() as conn:
            return cast(
                "sqlite3.Row | None",
                conn.execute(query, params).fetchone(),
            )

    def fetch_all(self, query: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self.get_connection() as conn:
            return cast(
                "list[sqlite3.Row]",
                conn.execute(query, params).fetchall(),
            )

    def create_tables(self, schema: str) -> None:
        with self.get_connection() as conn:
            conn.executescript(schema)


database = Database(db_path="Database.sqlite3")
