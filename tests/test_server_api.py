from fastapi.testclient import TestClient

from steam_playtime.config import Settings
from steam_playtime.server.app import create_app


def settings(tmp_path) -> Settings:
    return Settings(
        config_file=tmp_path / "config.toml",
        data_dir=tmp_path,
        device_id="local-device",
        device_name="local",
        check_interval_seconds=2,
        timezone="UTC",
        server_url="http://127.0.0.1:8080",
        server_host="127.0.0.1",
        server_port=8080,
        api_token="secret",
    )


def payload() -> dict:
    return {
        "device_id": "deck-id",
        "device_name": "deck",
        "sessions": [{
            "session_uuid": "session-id",
            "appid": "42",
            "game_name": "Example Game",
            "launch_kind": "STEAM_APP",
            "title_source": "LOCAL_MANIFEST",
            "start_time": "2026-01-01T10:00:00Z",
            "end_time": "2026-01-01T10:01:00Z",
            "duration_seconds": 60,
            "launch_command": "/private/path",
        }],
    }


def test_sync_endpoint_requires_token_and_accepts_valid_payload(tmp_path):
    client = TestClient(create_app(settings(tmp_path)))

    assert client.post("/api/v1/sessions", json=payload()).status_code == 401
    info = client.get("/api/v1/info", headers={"Authorization": "Bearer secret"})
    assert info.status_code == 200
    assert info.json()["server_id"]

    response = client.post("/api/v1/sessions", json=payload(), headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    assert response.json() == {"status": "success", "processed": 1}
