import csv

from typer.testing import CliRunner

from steam_playtime import cli
from steam_playtime.config import Settings
from steam_playtime.storage import server


def test_stats_csv_exports_daily_game_and_device_totals(tmp_path, monkeypatch):
    database = tmp_path / "server.db"
    server.save_sessions(
        database,
        "device-1",
        "PC, Main",
        [
            {
                "session_uuid": "session-1",
                "appid": "42",
                "game_name": 'Game, "Deluxe"',
                "launch_kind": "STEAM_APP",
                "title_source": "LOCAL_MANIFEST",
                "launch_target": None,
                "start_time": "2026-01-01T23:30:00Z",
                "end_time": "2026-01-02T01:00:00Z",
                "duration_seconds": 5400,
            }
        ],
    )
    configuration = Settings(
        config_file=tmp_path / "config.toml",
        data_dir=tmp_path,
        device_id="local-device",
        device_name="Local device",
        check_interval_seconds=2,
        timezone="UTC",
        server_url="",
        server_host="127.0.0.1",
        server_port=8080,
        api_token="token",
    )
    monkeypatch.setattr(cli, "settings", lambda: configuration)
    output = tmp_path / "playtime.csv"

    result = CliRunner().invoke(cli.app, ["stats", "--csv", str(output)])

    assert result.exit_code == 0
    assert f"Exported 2 row(s) to {output}." in result.output
    with output.open(newline="", encoding="utf-8") as exported:
        assert list(csv.DictReader(exported)) == [
            {
                "day": "2026-01-01",
                "game_name": 'Game, "Deluxe"',
                "device_name": "PC, Main",
                "duration_seconds": "1800",
                "duration": "00:30:00",
            },
            {
                "day": "2026-01-02",
                "game_name": 'Game, "Deluxe"',
                "device_name": "PC, Main",
                "duration_seconds": "3600",
                "duration": "01:00:00",
            },
        ]
