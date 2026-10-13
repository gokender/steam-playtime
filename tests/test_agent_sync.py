from datetime import UTC, datetime

import httpx
import pytest

from steam_playtime.agent import sync
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


def test_http_error_suspends_server_until_reset(tmp_path, monkeypatch):
    configuration = Settings(
        config_file=tmp_path / "config.toml",
        data_dir=tmp_path,
        device_id="device",
        device_name="device",
        check_interval_seconds=2,
        timezone="UTC",
        server_url="http://server",
        server_host="127.0.0.1",
        server_port=8080,
        api_token="token",
    )
    now = datetime(2026, 1, 1, tzinfo=UTC)

    class FailingResponse:
        def raise_for_status(self):
            request = httpx.Request("GET", "http://server/api/v1/info")
            response = httpx.Response(500, request=request)
            raise httpx.HTTPStatusError("server error", request=request, response=response)

    class FailingClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def get(self, *_args, **_kwargs):
            return FailingResponse()

    monkeypatch.setattr(sync.httpx, "Client", FailingClient)

    assert sync.sync_once(configuration, now) == 0
    state = storage.server_sync_status(configuration.agent_db, "http://server")
    assert state["suspended"]
    assert state["failure_count"] == 1
    assert not storage.server_is_ready(configuration.agent_db, "http://server", now)
    assert storage.last_sync_result(configuration.agent_db, "http://server") == {
        "result": "FAILED",
        "attempted_at": "2026-01-01T00:00:00Z",
        "session_count": 0,
        "error": "server error",
    }

    assert storage.reset_server_sync(configuration.agent_db, "http://server")
    assert storage.server_is_ready(configuration.agent_db, "http://server", now)
    assert storage.server_sync_status(configuration.agent_db, "http://server")["failure_count"] == 0


def test_operational_state_is_persisted_per_configured_server(tmp_path):
    db_path = tmp_path / "agent.db"
    now = datetime(2026, 1, 1, tzinfo=UTC)
    with storage.connection(db_path) as database:
        database.execute(
            "INSERT INTO sessions (session_uuid, device_id, appid, launch_command, game_name, launch_kind, "
            "title_source, start_time, end_time, duration_seconds, status) "
            "VALUES ('session-1', 'device-1', '42', '', 'Example', 'UNKNOWN', 'FALLBACK', ?, ?, 60, 'PENDING')",
            ("2026-01-01T10:00:00Z", "2026-01-01T10:01:00Z"),
        )

    storage.record_agent_heartbeat(db_path, now, "http://server")
    storage.record_sync_result(db_path, "http://server", "SUCCESS", now, 0)

    assert storage.agent_heartbeat(db_path) == "2026-01-01T00:00:00Z"
    assert storage.active_server_url(db_path) == "http://server"
    assert storage.pending_session_count(db_path, None) == 1
    assert storage.last_sync_result(db_path, "http://server") == {
        "result": "SUCCESS",
        "attempted_at": "2026-01-01T00:00:00Z",
        "session_count": 0,
        "error": None,
    }
