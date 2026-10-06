import socket

import pytest

from steam_playtime.cli import bind_server_socket
from steam_playtime.config import Settings


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
