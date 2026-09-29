"""SQLite schema and transaction helpers.

The schema is intentionally created from scratch during development. Existing
databases are not migrated; delete the database before changing this schema.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path


def get_db(db_file: Path) -> sqlite3.Connection:
    """Open a SQLite connection configured for row access."""
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_file, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def database(db_file: Path):
    """Provide a transaction and always close its connection."""
    conn = get_db(db_file)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db(db_file: Path) -> None:
    """Create the development schema if the database does not yet contain it."""
    with database(db_file) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                appid TEXT NOT NULL,
                launch_command TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT,
                duration_seconds REAL,
                status TEXT CHECK(status IN ('RUNNING', 'COMPLETED', 'SYNCED')) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ingested_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_inode TEXT NOT NULL,
                source_offset INTEGER NOT NULL,
                event_type TEXT CHECK(event_type IN ('START', 'STOP')) NOT NULL,
                event_time TEXT NOT NULL,
                source_appid TEXT NOT NULL,
                appid TEXT NOT NULL,
                launch_command TEXT,
                raw_line TEXT NOT NULL,
                session_id INTEGER REFERENCES sessions(id) ON DELETE SET NULL,
                ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(source_inode, source_offset)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS events_session_id ON ingested_events(session_id)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    """Read an ingestion-state value."""
    row = conn.execute("SELECT value FROM metadata WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    """Store an ingestion-state value."""
    conn.execute(
        "INSERT INTO metadata (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
