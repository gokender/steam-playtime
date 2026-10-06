"""Persistence operations for the central server."""

import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path

from steam_playtime.storage.schema import create_server_schema


@contextmanager
def connection(db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    database = sqlite3.connect(db_path)
    database.row_factory = sqlite3.Row
    try:
        create_server_schema(database)
        yield database
        database.commit()
    finally:
        database.close()


def server_id(db_path: Path) -> str:
    """Return the immutable identity of this server database."""
    with connection(db_path) as database:
        row = database.execute("SELECT value FROM metadata WHERE key = 'server_id'").fetchone()
        if row:
            return row["value"]
        value = str(uuid.uuid4())
        database.execute("INSERT INTO metadata (key, value) VALUES ('server_id', ?)", (value,))
        return value


def save_sessions(db_path: Path, device_id: str, device_name: str, sessions: list[dict]) -> None:
    with connection(db_path) as database:
        owner = database.execute("SELECT device_id FROM devices WHERE device_name = ?", (device_name,)).fetchone()
        if owner and owner["device_id"] != device_id:
            raise ValueError("This device_name is already used by another device.")
        database.execute(
            "INSERT INTO devices (device_id, device_name) VALUES (?, ?) "
            "ON CONFLICT(device_id) DO UPDATE SET device_name = excluded.device_name, updated_at = CURRENT_TIMESTAMP",
            (device_id, device_name),
        )
        database.executemany(
            "INSERT OR IGNORE INTO sessions (session_uuid, device_id, appid, game_name_snapshot, launch_kind, "
            "title_source, launch_target, start_time, end_time, duration_seconds) "
            "VALUES (:session_uuid, :device_id, :appid, :game_name, :launch_kind, :title_source, :launch_target, "
            ":start_time, :end_time, :duration_seconds)",
            [{**session, "device_id": device_id} for session in sessions],
        )
        for session in sessions:
            if session["launch_kind"] == "STEAM_APP" and session["title_source"] == "LOCAL_MANIFEST":
                database.execute(
                    "INSERT INTO steam_apps (appid, name, resolution_status, resolution_source) VALUES (?, ?, 'RESOLVED', 'LOCAL_MANIFEST') "
                    "ON CONFLICT(appid) DO UPDATE SET name = excluded.name, resolution_status = 'RESOLVED', resolution_source = 'LOCAL_MANIFEST'",
                    (int(session["appid"]), session["game_name"]),
                )
            elif session["launch_kind"] == "UNKNOWN":
                database.execute(
                    "INSERT OR IGNORE INTO steam_apps (appid, resolution_status) VALUES (?, 'PENDING')",
                    (int(session["appid"]),),
                )


def pending_appids(db_path: Path) -> list[int]:
    with connection(db_path) as database:
        rows = database.execute(
            "SELECT appid FROM steam_apps WHERE resolution_status = 'PENDING' "
            "OR (resolution_status = 'RETRY_LATER' AND next_lookup_at <= CURRENT_TIMESTAMP)"
        ).fetchall()
    return [row["appid"] for row in rows]


def history(db_path: Path, limit: int) -> list[sqlite3.Row]:
    with connection(db_path) as database:
        return database.execute(
            "SELECT s.start_time, COALESCE(a.name, s.game_name_snapshot) AS game_name, d.device_name, s.duration_seconds "
            "FROM sessions s JOIN devices d ON d.device_id = s.device_id "
            "LEFT JOIN steam_apps a ON a.appid = CAST(s.appid AS INTEGER) "
            "ORDER BY s.start_time DESC LIMIT ?",
            (limit,),
        ).fetchall()


def statistics(db_path: Path) -> list[sqlite3.Row]:
    with connection(db_path) as database:
        return database.execute(
            "SELECT COALESCE(a.name, s.game_name_snapshot) AS game_name, SUM(s.duration_seconds) AS duration "
            "FROM sessions s LEFT JOIN steam_apps a ON a.appid = CAST(s.appid AS INTEGER) "
            "GROUP BY game_name ORDER BY duration DESC"
        ).fetchall()


def sessions_for_reporting(db_path: Path) -> list[sqlite3.Row]:
    """Read resolved names, devices, and UTC intervals for daily reports."""
    with connection(db_path) as database:
        return database.execute(
            "SELECT s.start_time, s.end_time, d.device_name, "
            "COALESCE(a.name, s.game_name_snapshot) AS game_name "
            "FROM sessions s JOIN devices d ON d.device_id = s.device_id "
            "LEFT JOIN steam_apps a ON a.appid = CAST(s.appid AS INTEGER) "
            "ORDER BY s.start_time DESC"
        ).fetchall()
