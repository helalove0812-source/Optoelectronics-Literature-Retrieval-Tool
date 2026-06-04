import sqlite3
from pathlib import Path


def get_schema_path() -> Path:
    return Path(__file__).resolve().parents[3] / "sql" / "schema.sql"


def resolve_sqlite_path(database_url: str) -> Path:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError(f"Unsupported database URL: {database_url}")
    return Path(database_url.removeprefix(prefix))


def connect_sqlite(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(db_path)


def _has_column(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
) -> bool:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(row[1] == column_name for row in rows)


def _run_lightweight_migrations(connection: sqlite3.Connection) -> None:
    if not _has_column(connection, "papers", "zh_summary"):
        connection.execute("ALTER TABLE papers ADD COLUMN zh_summary TEXT")
    if not _has_column(connection, "push_log", "topic_id"):
        connection.execute(
            "ALTER TABLE push_log ADD COLUMN topic_id TEXT NOT NULL DEFAULT ''"
        )
    if not _has_column(connection, "push_log", "subscriber_email"):
        connection.execute(
            "ALTER TABLE push_log ADD COLUMN subscriber_email TEXT NOT NULL DEFAULT ''"
        )


def initialize_database(db_path: Path) -> None:
    schema = get_schema_path().read_text(encoding="utf-8")

    with connect_sqlite(db_path) as connection:
        connection.executescript(schema)
        _run_lightweight_migrations(connection)
