"""TOML configuration created automatically on first use."""

import os
import secrets
import socket
import tomllib
import uuid
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_config_path, user_data_path


@dataclass(frozen=True)
class Settings:
    config_file: Path
    data_dir: Path
    device_id: str
    device_name: str
    check_interval_seconds: float
    timezone: str
    server_url: str
    server_host: str
    server_port: int
    api_token: str

    @property
    def agent_db(self) -> Path:
        return self.data_dir / "agent.db"

    @property
    def server_db(self) -> Path:
        return self.data_dir / "server.db"


def config_path() -> Path:
    return Path(os.getenv("STEAM_PLAYTIME_CONFIG", user_config_path("steam-playtime") / "config.toml"))


def _device_name(device_id: str) -> str:
    words = ("otter", "moon", "cedar", "fox", "maple", "cloud", "river", "cat", "stone", "plane", "grass", "dog")
    suffix = "-".join(words[value % len(words)] for value in uuid.UUID(device_id).bytes[:2])
    hostname = "".join(character.lower() if character.isalnum() else "-" for character in socket.gethostname()).strip("-")
    return f"{hostname or 'device'}-{suffix}"


def _default_document() -> dict:
    device_id = str(uuid.uuid4())
    return {
        "agent": {
            "device_id": device_id,
            "device_name": _device_name(device_id),
            "check_interval_seconds": 2,
            "timezone": os.getenv("TZ", "UTC"),
        },
        "server": {
            "url": "",
            "host": "127.0.0.1",
            "port": 8080,
            "api_token": secrets.token_urlsafe(32),
        },
    }


def _write_config(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    agent = document["agent"]
    server = document["server"]
    content = (
        "# Created automatically by steam-playtime. Keep this file private.\n\n"
        "[agent]\n"
        f'device_id = "{agent["device_id"]}"\n'
        f'device_name = "{agent["device_name"]}"\n'
        f'check_interval_seconds = {agent["check_interval_seconds"]}\n'
        f'timezone = "{agent["timezone"]}"\n\n'
        "[server]\n"
        f'url = "{server["url"]}"\n'
        f'host = "{server["host"]}"\n'
        f'port = {server["port"]}\n'
        f'api_token = "{server["api_token"]}"\n'
    )
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)


def load_settings() -> Settings:
    path = config_path()
    if not path.exists():
        _write_config(path, _default_document())
    with path.open("rb") as config_file:
        document = tomllib.load(config_file)
    agent = document["agent"]
    server = document["server"]
    data_dir = Path(os.getenv("STEAM_PLAYTIME_DATA_DIR", user_data_path("steam-playtime")))
    return Settings(
        config_file=path,
        data_dir=data_dir,
        device_id=os.getenv("DEVICE_ID") or agent["device_id"],
        device_name=os.getenv("DEVICE_NAME") or agent["device_name"],
        check_interval_seconds=float(os.getenv("CHECK_INTERVAL") or agent["check_interval_seconds"]),
        timezone=os.getenv("TIMEZONE") or agent["timezone"],
        server_url=(os.getenv("SERVER_URL") or server["url"]).rstrip("/"),
        server_host=os.getenv("SERVER_HOST") or server["host"],
        server_port=int(os.getenv("SERVER_PORT") or server["port"]),
        api_token=os.getenv("API_TOKEN") or server["api_token"],
    )
