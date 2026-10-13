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
    assert "Synchronization: suspended" in status.output
    assert "sync reset" in status.output

    reset = runner.invoke(cli.app, ["sync", "reset"])
    assert reset.exit_code == 0
    assert "Synchronization reset" in reset.output
    assert agent_storage.server_is_ready(configuration.agent_db, configuration.server_url, datetime.now(UTC))
