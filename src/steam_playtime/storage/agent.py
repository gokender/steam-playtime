"""Persistence operations for one local collector."""

import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path

from steam_playtime.storage.schema import create_agent_schema


@contextmanager
def connection(db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    database = sqlite3.connect(db_path)
    database.row_factory = sqlite3.Row
    try:
        create_agent_schema(database)
        yield database
        database.commit()
    finally:
        database.close()


def metadata(database: sqlite3.Connection, key: str) -> str | None:
    row = database.execute("SELECT value FROM metadata WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_metadata(database: sqlite3.Connection, key: str, value: str) -> None:
    database.execute(
        "INSERT INTO metadata (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def pending_sessions(db_path: Path, batch_size: int = 100) -> list[dict]:
    with connection(db_path) as database:
        rows = database.execute(
            "SELECT session_uuid, appid, game_name, launch_kind, title_source, launch_target, start_time, end_time, "
            "duration_seconds FROM sessions WHERE status = 'PENDING' ORDER BY id LIMIT ?",
            (batch_size,),
        ).fetchall()
    return [dict(row) for row in rows]


def mark_synced(db_path: Path, session_uuids: list[str]) -> None:
    with connection(db_path) as database:
        database.executemany("UPDATE sessions SET status = 'SYNCED' WHERE session_uuid = ?", [(value,) for value in session_uuids])


def close_running_session(database: sqlite3.Connection, session: sqlite3.Row, end_time: str) -> float:
    from datetime import datetime

    start = datetime.fromisoformat(session["start_time"].replace("Z", "+00:00"))
    end = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
    duration = max(0.0, (end - start).total_seconds())
    database.execute(
        "UPDATE sessions SET session_uuid = ?, end_time = ?, duration_seconds = ?, status = 'PENDING' WHERE id = ?",
        (str(uuid.uuid4()), end_time, duration, session["id"]),
    )
    return duration
