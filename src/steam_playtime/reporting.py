"""Human-readable server reports with timezone-aware daily totals."""

import csv
from collections import defaultdict
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


def format_duration(seconds: float) -> str:
    """Render a duration with total hours, including durations over one day."""
    total_seconds = round(seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def split_session_by_day(start_time: str, end_time: str, timezone: str) -> list[tuple[str, float, datetime, datetime]]:
    """Split a UTC session at local midnights for accurate daily reporting."""
    zone = ZoneInfo(timezone)
    current = datetime.fromisoformat(start_time.replace("Z", "+00:00")).astimezone(zone)
    end = datetime.fromisoformat(end_time.replace("Z", "+00:00")).astimezone(zone)
    segments: list[tuple[str, float, datetime, datetime]] = []

    while current.date() < end.date():
        next_day = current.date() + timedelta(days=1)
        midnight = datetime.combine(next_day, time.min, tzinfo=zone)
        duration = (midnight.astimezone(UTC) - current.astimezone(UTC)).total_seconds()
        segments.append((current.date().isoformat(), duration, current, midnight))
        current = midnight

    duration = (end.astimezone(UTC) - current.astimezone(UTC)).total_seconds()
    segments.append((current.date().isoformat(), max(0, duration), current, end))
    return segments


def daily_totals(rows, timezone: str, game_name: str | None = None) -> dict[str, dict]:
    """Return daily totals with games merged across sessions and devices."""
    totals: dict[str, dict] = defaultdict(lambda: {"duration": 0.0, "session_count": 0, "games": {}})
    for row in rows:
        if game_name and row["game_name"].casefold() != game_name.casefold():
            continue
        for day, duration, _, _ in split_session_by_day(row["start_time"], row["end_time"], timezone):
            totals[day]["duration"] += duration
            totals[day]["session_count"] += 1
            game = totals[day]["games"].setdefault(row["game_name"], {"duration": 0.0, "session_count": 0})
            game["duration"] += duration
            game["session_count"] += 1
    return {
        day: {
            "duration": total["duration"],
            "session_count": total["session_count"],
            "games": [
                {"game_name": name, **game}
                for name, game in sorted(total["games"].items(), key=lambda item: (-item[1]["duration"], item[0].casefold()))
            ],
        }
        for day, total in totals.items()
    }


def daily_game_device_totals(rows, timezone: str, game_name: str | None = None) -> list[dict]:
    """Aggregate sessions by local day, resolved game name, and device name."""
    totals: dict[tuple[str, str, str], float] = defaultdict(float)
    for row in rows:
        if game_name and row["game_name"].casefold() != game_name.casefold():
            continue
        for day, duration, _, _ in split_session_by_day(row["start_time"], row["end_time"], timezone):
            totals[(day, row["game_name"], row["device_name"])] += duration

    return [
        {
            "day": day,
            "game_name": name,
            "device_name": device,
            "duration_seconds": duration,
            "duration": format_duration(duration),
        }
        for (day, name, device), duration in sorted(totals.items())
    ]


def write_daily_game_device_csv(path: Path, totals: list[dict]) -> None:
    """Write daily game/device totals as an RFC 4180-compatible CSV file."""
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(
            output,
            fieldnames=["day", "game_name", "device_name", "duration_seconds", "duration"],
            lineterminator="\n",
        )
        writer.writeheader()
        for total in totals:
            writer.writerow(
                {
                    **total,
                    "duration_seconds": f"{total['duration_seconds']:g}",
                }
            )
