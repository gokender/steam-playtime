from datetime import UTC, datetime

import pytest

from steam_playtime.config import Settings
from steam_playtime.storage import agent as storage


def test_sessions_are_delivered_once_per_server(tmp_path):
    db_path = tmp_path / "agent.db"
    with storage.connection(db_path) as database:
        database.execute(
            "INSERT INTO sessions (session_uuid, device_id, appid, launch_command, game_name, launch_kind, "
            "title_source, start_time, end_time, duration_seconds, status) "
            "VALUES ('session-1', 'device-1', '42', '', 'Example', 'UNKNOWN', 'FALLBACK', ?, ?, 60, 'PENDING')",
            ("2026-01-01T10:00:00Z", "2026-01-01T10:01:00Z"),
        )

    now = datetime.now(UTC)
    storage.mark_synced(db_path, "server-a", ["session-1"], now)

    assert storage.pending_sessions(db_path, "server-a") == []
    assert [session["session_uuid"] for session in storage.pending_sessions(db_path, "server-b")] == ["session-1"]


def test_failed_server_uses_backoff(tmp_path):
    db_path = tmp_path / "agent.db"
    now = datetime(2026, 1, 1, tzinfo=UTC)

    storage.record_server_failure(db_path, "http://server", "not found", now)

    assert not storage.server_is_ready(db_path, "http://server", now)
    assert storage.server_is_ready(db_path, "http://server", datetime(2026, 1, 1, 0, 1, tzinfo=UTC))
