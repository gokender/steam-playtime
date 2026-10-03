"""Human-readable server reports with timezone-aware daily totals."""

from collections import defaultdict
from datetime import UTC, datetime, time, timedelta
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
    """Return daily duration and contributing sessions, optionally for one game."""
    totals: dict[str, dict] = defaultdict(lambda: {"duration": 0.0, "sessions": []})
    for row in rows:
        if game_name and row["game_name"].casefold() != game_name.casefold():
            continue
        for day, duration, segment_start, segment_end in split_session_by_day(row["start_time"], row["end_time"], timezone):
            totals[day]["duration"] += duration
            totals[day]["sessions"].append(
                {
                    "game_name": row["game_name"],
                    "duration": duration,
                    "start": segment_start.strftime("%H:%M:%S"),
                    "end": segment_end.strftime("%H:%M:%S"),
                }
            )
    return dict(totals)
