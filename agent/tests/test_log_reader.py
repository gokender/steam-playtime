import sqlite3

import pytest

from config import Config
from database import init_db
from log_reader import read_logs


@pytest.fixture
def agent_config(tmp_path):
    config = Config(tmp_path / "gameprocess_log.txt", tmp_path / "agent.db", 0.1)
    init_db(config.db_file)
    return config


def read_rows(db_file, query):
    with sqlite3.connect(db_file) as conn:
        return conn.execute(query).fetchall()


def test_closes_matching_appid_and_keeps_event_audit_trail(agent_config):
    agent_config.log_file.write_text(
        '[2026-01-01 10:00:00] AppID 10 adding PID 1 as a tracked process "first"\n'
        '[2026-01-01 10:01:00] AppID 20 adding PID 2 as a tracked process "second"\n'
        '[2026-01-01 10:02:00] Remove 10 from running list\n'
        '[2026-01-01 10:03:00] Remove 20 from running list\n'
    )

    read_logs(agent_config)

    assert read_rows(
        agent_config.db_file,
        "SELECT appid, start_time, end_time, duration_seconds, status FROM sessions ORDER BY id",
    ) == [
        ("10", "2026-01-01 10:00:00", "2026-01-01 10:02:00", 120.0, "COMPLETED"),
        ("20", "2026-01-01 10:01:00", "2026-01-01 10:03:00", 120.0, "COMPLETED"),
    ]
    assert read_rows(
        agent_config.db_file,
        "SELECT event_type, source_appid, appid, session_id IS NOT NULL FROM ingested_events ORDER BY id",
    ) == [
        ("START", "10", "10", 1),
        ("START", "20", "20", 1),
        ("STOP", "10", "10", 1),
        ("STOP", "20", "20", 1),
    ]


def test_matches_a_non_steam_shortcut_start_to_its_signed_stop_appid(agent_config):
    agent_config.log_file.write_text(
        '[2026-08-04 14:45:58] AppID 14209595030481403904 adding PID 18837 as a tracked process '
        '"/home/deck/.local/share/Steam/ubuntu12_32/reaper SteamLaunch AppId=3308429157 -- '
        '\"/usr/bin/flatpak\" run org.libretro.RetroArch"\n'
        '[2026-08-04 14:47:08] Remove -986538139 from running list\n'
    )

    read_logs(agent_config)

    assert read_rows(
        agent_config.db_file,
        "SELECT appid, start_time, end_time, duration_seconds, status FROM sessions",
    ) == [("3308429157", "2026-08-04 14:45:58", "2026-08-04 14:47:08", 70.0, "COMPLETED")]
    assert read_rows(
        agent_config.db_file,
        "SELECT event_type, source_appid, appid FROM ingested_events ORDER BY id",
    ) == [
        ("START", "14209595030481403904", "3308429157"),
        ("STOP", "-986538139", "3308429157"),
    ]


def test_defers_an_incomplete_final_line(agent_config):
    agent_config.log_file.write_text('[2026-01-01 10:00:00] AppID 10 adding PID 1 as a tracked process "first"')

    read_logs(agent_config)
    assert read_rows(agent_config.db_file, "SELECT * FROM sessions") == []

    with agent_config.log_file.open("a") as log_file:
        log_file.write("\n[2026-01-01 10:05:00] Remove 10 from running list\n")
    read_logs(agent_config)

    assert read_rows(agent_config.db_file, "SELECT duration_seconds, status FROM sessions") == [(300.0, "COMPLETED")]


def test_repeated_read_does_not_duplicate_events_or_sessions(agent_config):
    agent_config.log_file.write_text(
        '[2026-01-01 10:00:00] AppID 10 adding PID 1 as a tracked process "first"\n'
        '[2026-01-01 10:05:00] Remove 10 from running list\n'
    )

    read_logs(agent_config)
    read_logs(agent_config)

    assert read_rows(agent_config.db_file, "SELECT COUNT(*) FROM sessions") == [(1,)]
    assert read_rows(agent_config.db_file, "SELECT COUNT(*) FROM ingested_events") == [(2,)]
