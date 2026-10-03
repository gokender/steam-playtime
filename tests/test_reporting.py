from steam_playtime.reporting import daily_totals, format_duration, split_session_by_day


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
