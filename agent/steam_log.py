"""Steam gameprocess_log parsing."""

import re
from dataclasses import dataclass

START_PATTERN = re.compile(
    r'^\[(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] '
    r'AppID (?P<appid>\d+) adding PID \d+ as a tracked process "(?P<command>.*)"$'
)
STOP_PATTERN = re.compile(
    r"^\[(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] "
    r"Remove (?P<appid>-?\d+) from running list$"
)


@dataclass(frozen=True)
class SteamEvent:
    event_type: str
    event_time: str
    appid: str
    raw_line: str
    launch_command: str | None = None


def parse_line(line: str) -> SteamEvent | None:
    """Return a recognized Steam start or stop event, otherwise ``None``."""
    raw_line = line.strip()
    start = START_PATTERN.match(raw_line)
    if start:
        data = start.groupdict()
        return SteamEvent("START", data["timestamp"], data["appid"], raw_line, data["command"])

    stop = STOP_PATTERN.match(raw_line)
    if stop:
        data = stop.groupdict()
        return SteamEvent("STOP", data["timestamp"], data["appid"], raw_line)
    return None
