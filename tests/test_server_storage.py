import sqlite3

import pytest

from steam_playtime.storage import server
from steam_playtime.steam.catalog import _save


def session(session_uuid: str = "session-1") -> dict:
    return {
        "session_uuid": session_uuid,
        "appid": "42",
        "game_name": "Example Game",
        "launch_kind": "STEAM_APP",
        "title_source": "LOCAL_MANIFEST",
        "launch_target": None,
        "start_time": "2026-01-01T10:00:00Z",
        "end_time": "2026-01-01T10:01:00Z",
        "duration_seconds": 60,
    }


def test_sessions_are_idempotent_and_raw_commands_are_not_stored(tmp_path):
    database = tmp_path / "server.db"
    server.save_sessions(database, "device-1", "deck", [session()])
    server.save_sessions(database, "device-1", "deck", [session()])

    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM sessions").fetchone() == (1,)
        assert connection.execute("SELECT name FROM steam_apps WHERE appid = 42").fetchone() == ("Example Game",)
        fields = {field[1] for field in connection.execute("PRAGMA table_info(sessions)")}
    assert "launch_command" not in fields


def test_device_names_are_unique(tmp_path):
    database = tmp_path / "server.db"
    server.save_sessions(database, "device-1", "deck", [session()])

    with pytest.raises(ValueError, match="device_name"):
        server.save_sessions(database, "device-2", "deck", [session("session-2")])


def test_catalog_resolution_updates_fallback_session_snapshots(tmp_path):
    database = tmp_path / "server.db"
    unknown = {**session(), "game_name": "AppID 42", "launch_kind": "UNKNOWN", "title_source": "FALLBACK"}
    server.save_sessions(database, "device-1", "deck", [unknown])

    from datetime import UTC, datetime

    _save(database, 42, "Resolved Game", "game", "RESOLVED", "STEAM_STORE", datetime.now(UTC), None)
    with sqlite3.connect(database) as connection:
        row = connection.execute("SELECT game_name_snapshot, launch_kind, title_source FROM sessions").fetchone()
    assert row == ("Resolved Game", "STEAM_APP", "SERVER_CATALOG")


def test_reporting_sessions_include_device_name(tmp_path):
    database = tmp_path / "server.db"
    server.save_sessions(database, "device-1", "Steam Deck", [session()])

    rows = server.sessions_for_reporting(database)

    assert rows[0]["game_name"] == "Example Game"
    assert rows[0]["device_name"] == "Steam Deck"
