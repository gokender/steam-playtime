import logging

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


def test_sync_endpoint_requires_token_and_accepts_valid_payload(tmp_path, caplog):
    client = TestClient(create_app(settings(tmp_path)))
    caplog.set_level(logging.INFO, logger="steam_playtime.server.app")

    assert client.post("/api/v1/sessions", json=payload()).status_code == 401
    info = client.get("/api/v1/info", headers={"Authorization": "Bearer secret"})
    assert info.status_code == 200
    assert info.json()["server_id"]

    response = client.post("/api/v1/sessions", json=payload(), headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    assert response.json() == {"status": "success", "processed": 1}
    assert "server | sessions_ingested | device=deck | processed=1" in caplog.messages


def test_reporting_endpoints_are_authenticated_and_history_is_paginated(tmp_path):
    client = TestClient(create_app(settings(tmp_path)))
    headers = {"Authorization": "Bearer secret"}
    first = payload()
    second = payload()
    second["sessions"][0]["session_uuid"] = "session-id-2"
    second["sessions"][0]["appid"] = "43"
    second["sessions"][0]["game_name"] = "Second Game"
    second["sessions"][0]["start_time"] = "2026-01-01T11:00:00Z"

    client.post("/api/v1/sessions", json=first, headers=headers)
    client.post("/api/v1/sessions", json=second, headers=headers)

    assert client.get("/api/v1/history").status_code == 401
    page_one = client.get("/api/v1/history?limit=1", headers=headers)
    assert page_one.status_code == 200
    assert page_one.json()["sessions"] == [{
        "start_time": "2026-01-01T11:00:00Z",
        "game_name": "Second Game",
        "device_name": "deck",
        "duration_seconds": 60.0,
    }]
    assert "launch_command" not in page_one.json()["sessions"][0]

    page_two = client.get("/api/v1/history", params={"limit": 1, "cursor": page_one.json()["next_cursor"]}, headers=headers)
    assert page_two.status_code == 200
    assert page_two.json()["sessions"][0]["game_name"] == "Example Game"

    stats = client.get("/api/v1/stats", headers=headers)
    assert {row["game_name"] for row in stats.json()["rows"]} == {"Example Game", "Second Game"}
    daily = client.get("/api/v1/stats/daily", params={"timezone": "UTC"}, headers=headers)
    assert daily.status_code == 200
    assert daily.json()["totals"][0]["day"] == "2026-01-01"
