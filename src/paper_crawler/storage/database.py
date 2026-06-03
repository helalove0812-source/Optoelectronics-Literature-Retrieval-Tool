import sqlite3
from pathlib import Path


def get_schema_path() -> Path:
    return Path(__file__).resolve().parents[3] / "sql" / "schema.sql"


def connect_sqlite(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(db_path)


def initialize_database(db_path: Path) -> None:
    schema = get_schema_path().read_text(encoding="utf-8")

    with connect_sqlite(db_path) as connection:
        connection.executescript(schema)
