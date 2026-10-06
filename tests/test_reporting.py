import csv

from steam_playtime.reporting import (
    daily_game_device_totals,
    daily_totals,
    format_duration,
    split_session_by_day,
    write_daily_game_device_csv,
)


def test_duration_has_total_hours():
    assert format_duration(98134) == "27:15:34"


def test_session_crossing_midnight_is_split_in_reporting_timezone():
    segments = split_session_by_day("2026-01-01T22:30:00Z", "2026-01-02T01:00:00Z", "Europe/Paris")

    assert [(day, duration) for day, duration, _, _ in segments] == [
        ("2026-01-01", 1800.0),
        ("2026-01-02", 7200.0),
    ]


def test_daily_totals_include_session_details():
    rows = [{"game_name": "Example", "start_time": "2026-01-01T10:00:00Z", "end_time": "2026-01-01T11:00:00Z"}]

    totals = daily_totals(rows, "UTC", "Example")

    assert totals["2026-01-01"]["duration"] == 3600
    assert totals["2026-01-01"]["sessions"][0]["start"] == "10:00:00"


def test_daily_game_device_totals_split_and_group_by_game_and_device():
    rows = [
        {
            "game_name": "Example",
            "device_name": "Deck",
            "start_time": "2026-01-01T23:30:00Z",
            "end_time": "2026-01-02T01:00:00Z",
        },
        {
            "game_name": "Example",
            "device_name": "Deck",
            "start_time": "2026-01-02T02:00:00Z",
            "end_time": "2026-01-02T02:30:00Z",
        },
        {
            "game_name": "Other",
            "device_name": "Desktop",
            "start_time": "2026-01-02T10:00:00Z",
            "end_time": "2026-01-02T11:00:00Z",
        },
    ]

    assert daily_game_device_totals(rows, "UTC") == [
        {"day": "2026-01-01", "game_name": "Example", "device_name": "Deck", "duration_seconds": 1800.0, "duration": "00:30:00"},
        {"day": "2026-01-02", "game_name": "Example", "device_name": "Deck", "duration_seconds": 5400.0, "duration": "01:30:00"},
        {"day": "2026-01-02", "game_name": "Other", "device_name": "Desktop", "duration_seconds": 3600.0, "duration": "01:00:00"},
    ]


def test_csv_export_escapes_game_and_device_names(tmp_path):
    path = tmp_path / "playtime.csv"
    totals = [
        {
            "day": "2026-01-02",
            "game_name": 'Game, "Deluxe"',
            "device_name": "PC, Main",
            "duration_seconds": 7200.0,
            "duration": "02:00:00",
        }
    ]

    write_daily_game_device_csv(path, totals)

    with path.open(newline="", encoding="utf-8") as exported:
        assert list(csv.DictReader(exported)) == [
            {
                "day": "2026-01-02",
                "game_name": 'Game, "Deluxe"',
                "device_name": "PC, Main",
                "duration_seconds": "7200",
                "duration": "02:00:00",
            }
        ]
