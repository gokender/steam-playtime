"""Persistence operations for one local collector."""

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
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


def server_is_ready(db_path: Path, url: str, now: datetime) -> bool:
    with connection(db_path) as database:
        suspended = database.execute(
            "SELECT 1 FROM sync_server_suspensions WHERE url = ?",
            (url,),
        ).fetchone()
        if suspended is not None:
            return False
        row = database.execute(
            "SELECT next_attempt_at FROM sync_servers WHERE url = ?",
            (url,),
        ).fetchone()
    if row is None or row["next_attempt_at"] is None:
        return True
    return datetime.fromisoformat(row["next_attempt_at"].replace("Z", "+00:00")) <= now


def server_id(db_path: Path, url: str) -> str | None:
    with connection(db_path) as database:
        row = database.execute("SELECT server_id FROM sync_servers WHERE url = ?", (url,)).fetchone()
    return row["server_id"] if row else None


def register_server(db_path: Path, url: str, server_id: str) -> None:
    with connection(db_path) as database:
        database.execute(
            "INSERT INTO sync_servers (url, server_id, failure_count, next_attempt_at, last_error) VALUES (?, ?, 0, NULL, NULL) "
            "ON CONFLICT(url) DO UPDATE SET server_id = excluded.server_id, failure_count = 0, "
            "next_attempt_at = NULL, last_error = NULL",
            (url, server_id),
        )
        database.execute("DELETE FROM sync_server_suspensions WHERE url = ?", (url,))


def record_server_failure(db_path: Path, url: str, error: str, now: datetime) -> None:
    with connection(db_path) as database:
        row = database.execute("SELECT failure_count FROM sync_servers WHERE url = ?", (url,)).fetchone()
        failures = (row["failure_count"] if row else 0) + 1
        delay_seconds = min(60 * 2 ** (failures - 1), 3600)
        next_attempt = now + timedelta(seconds=delay_seconds)
        database.execute(
            "INSERT INTO sync_servers (url, failure_count, next_attempt_at, last_error) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(url) DO UPDATE SET failure_count = excluded.failure_count, "
            "next_attempt_at = excluded.next_attempt_at, last_error = excluded.last_error",
            (url, failures, next_attempt.isoformat().replace("+00:00", "Z"), error),
        )


def suspend_server(db_path: Path, url: str, error: str, now: datetime) -> None:
    """Stop automatic retries after the server returned an HTTP error."""
    with connection(db_path) as database:
        row = database.execute("SELECT failure_count FROM sync_servers WHERE url = ?", (url,)).fetchone()
        failures = (row["failure_count"] if row else 0) + 1
        timestamp = now.isoformat().replace("+00:00", "Z")
        database.execute(
            "INSERT INTO sync_servers (url, failure_count, next_attempt_at, last_error) VALUES (?, ?, NULL, ?) "
            "ON CONFLICT(url) DO UPDATE SET failure_count = excluded.failure_count, "
            "next_attempt_at = NULL, last_error = excluded.last_error",
            (url, failures, error),
        )
        database.execute(
            "INSERT INTO sync_server_suspensions (url, suspended_at, error) VALUES (?, ?, ?) "
            "ON CONFLICT(url) DO UPDATE SET suspended_at = excluded.suspended_at, error = excluded.error",
            (url, timestamp, error),
        )


def reset_server_sync(db_path: Path, url: str) -> bool:
    """Clear retry and suspension state for one configured server."""
    with connection(db_path) as database:
        known = database.execute("SELECT 1 FROM sync_servers WHERE url = ?", (url,)).fetchone() is not None
        database.execute("DELETE FROM sync_server_suspensions WHERE url = ?", (url,))
        database.execute(
            "UPDATE sync_servers SET failure_count = 0, next_attempt_at = NULL, last_error = NULL WHERE url = ?",
            (url,),
        )
    return known


def server_sync_status(db_path: Path, url: str) -> dict[str, str | int | bool | None]:
    """Return persisted retry information for display by the CLI."""
    with connection(db_path) as database:
        row = database.execute(
            "SELECT s.failure_count, s.next_attempt_at, s.last_error, p.suspended_at "
            "FROM sync_servers s LEFT JOIN sync_server_suspensions p ON p.url = s.url WHERE s.url = ?",
            (url,),
        ).fetchone()
    if row is None:
        return {"known": False, "suspended": False, "failure_count": 0, "next_attempt_at": None, "last_error": None}
    return {
        "known": True,
        "suspended": row["suspended_at"] is not None,
        "failure_count": row["failure_count"],
        "next_attempt_at": row["next_attempt_at"],
        "last_error": row["last_error"],
    }


def pending_sessions(db_path: Path, server_id: str, batch_size: int = 100) -> list[dict]:
    with connection(db_path) as database:
        rows = database.execute(
            "SELECT s.session_uuid, s.appid, s.game_name, s.launch_kind, s.title_source, s.launch_target, "
            "s.start_time, s.end_time, s.duration_seconds FROM sessions s LEFT JOIN session_sync sync "
            "ON sync.session_uuid = s.session_uuid AND sync.server_id = ? "
            "WHERE s.end_time IS NOT NULL AND s.session_uuid IS NOT NULL "
            "AND (sync.status IS NULL OR sync.status != 'SYNCED') ORDER BY s.id LIMIT ?",
            (server_id, batch_size),
        ).fetchall()
    return [dict(row) for row in rows]


def mark_synced(db_path: Path, server_id: str, session_uuids: list[str], now: datetime) -> None:
    with connection(db_path) as database:
        database.executemany(
            "INSERT INTO session_sync (session_uuid, server_id, status, last_attempt_at, synced_at) VALUES (?, ?, 'SYNCED', ?, ?) "
            "ON CONFLICT(session_uuid, server_id) DO UPDATE SET status = 'SYNCED', "
            "last_attempt_at = excluded.last_attempt_at, synced_at = excluded.synced_at",
            [
                (value, server_id, now.isoformat().replace("+00:00", "Z"), now.isoformat().replace("+00:00", "Z"))
                for value in session_uuids
            ],
        )


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
