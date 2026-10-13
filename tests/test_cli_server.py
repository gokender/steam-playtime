import socket

import pytest
from typer.testing import CliRunner

from steam_playtime import cli
from steam_playtime.cli import bind_server_socket
from steam_playtime.config import Settings
from steam_playtime.storage import agent as agent_storage


def test_bind_server_socket_rejects_an_occupied_port(tmp_path):
    occupied = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupied.bind(("127.0.0.1", 0))
    occupied.listen()
    try:
        configuration = Settings(
            config_file=tmp_path / "config.toml",
            data_dir=tmp_path,
            device_id="device",
            device_name="device",
            check_interval_seconds=2,
            timezone="UTC",
            server_url="",
            server_host="127.0.0.1",
            server_port=occupied.getsockname()[1],
            api_token="token",
        )
        with pytest.raises(OSError):
            bind_server_socket(configuration)
    finally:
        occupied.close()


def test_status_shows_suspended_sync_and_reset_command(tmp_path, monkeypatch):
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
    from datetime import UTC, datetime

    agent_storage.suspend_server(configuration.agent_db, configuration.server_url, "server error", datetime.now(UTC))
    monkeypatch.setattr(cli, "settings", lambda: configuration)
    runner = CliRunner()

    status = runner.invoke(cli.app, ["status"])
    assert status.exit_code == 0
    assert "Current game: none" in status.output
    assert "Agent: never started" in status.output
    assert "Pending sessions: 0" in status.output
    assert "Synchronization: suspended" in status.output
    assert "sync reset" in status.output
    assert "Last synchronization: never" in status.output

    reset = runner.invoke(cli.app, ["sync", "reset"])
    assert reset.exit_code == 0
    assert "Synchronization reset" in reset.output
    assert agent_storage.server_is_ready(configuration.agent_db, configuration.server_url, datetime.now(UTC))


def test_status_uses_active_local_server_when_no_url_is_configured(tmp_path, monkeypatch):
    configuration = Settings(
        config_file=tmp_path / "config.toml",
        data_dir=tmp_path,
        device_id="device",
        device_name="device",
        check_interval_seconds=2,
        timezone="UTC",
        server_url="",
        server_host="127.0.0.1",
        server_port=8080,
        api_token="token",
    )
    from datetime import UTC, datetime

    agent_storage.record_agent_heartbeat(
        configuration.agent_db, datetime.now(UTC), "http://127.0.0.1:8080"
    )
    monkeypatch.setattr(cli, "settings", lambda: configuration)

    result = CliRunner().invoke(cli.app, ["status"])

    assert result.exit_code == 0
    assert "Agent: running" in result.output
    assert "Pending sessions: 0" in result.output
    assert "Synchronization: ready" in result.output
    assert "Last synchronization: never" in result.output


def test_history_uses_paginated_server_data(tmp_path, monkeypatch):
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
    responses = iter((
        {"sessions": [{"start_time": "2026-01-02T10:00:00Z", "game_name": "Two", "device_name": "deck", "duration_seconds": 60}], "next_cursor": "next"},
        {"sessions": [{"start_time": "2026-01-01T10:00:00Z", "game_name": "One", "device_name": "deck", "duration_seconds": 30}], "next_cursor": None},
    ))
    monkeypatch.setattr(cli, "settings", lambda: configuration)
    monkeypatch.setattr(cli, "server_request", lambda *_args, **_kwargs: next(responses))

    result = CliRunner().invoke(cli.app, ["history", "--limit", "2"])

    assert result.exit_code == 0
    assert "Two | deck | 00:01:00" in result.output
    assert "One | deck | 00:00:30" in result.output


def test_history_and_stats_can_use_completed_local_sessions(tmp_path, monkeypatch):
    configuration = Settings(
        config_file=tmp_path / "config.toml",
        data_dir=tmp_path,
        device_id="device",
        device_name="my-device",
        check_interval_seconds=2,
        timezone="UTC",
        server_url="http://server",
        server_host="127.0.0.1",
        server_port=8080,
        api_token="token",
    )
    with agent_storage.connection(configuration.agent_db) as database:
        database.execute(
            "INSERT INTO sessions (session_uuid, device_id, appid, launch_command, game_name, launch_kind, "
            "title_source, start_time, end_time, duration_seconds, status) "
            "VALUES ('local-1', 'device', '42', '', 'Local Game', 'UNKNOWN', 'FALLBACK', ?, ?, 90, 'PENDING')",
            ("2026-01-01T10:00:00Z", "2026-01-01T10:01:30Z"),
        )
    monkeypatch.setattr(cli, "settings", lambda: configuration)

    history = CliRunner().invoke(cli.app, ["history", "--local"])
    stats = CliRunner().invoke(cli.app, ["stats", "--local"])
    daily = CliRunner().invoke(cli.app, ["stats", "--local", "--daily"])

    assert history.exit_code == 0
    assert "Local Game | my-device | 00:01:30" in history.output
    assert stats.exit_code == 0
    assert "Local Game | 00:01:30" in stats.output
    assert daily.exit_code == 0
    assert "2026-01-01 | 00:01:30 | 1 session(s)" in daily.output
    assert "  Local Game | 00:01:30 | 1 session(s)" in daily.output
