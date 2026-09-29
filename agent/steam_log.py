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
STEAM_LAUNCH_APPID_PATTERN = re.compile(r"\bSteamLaunch AppId=(?P<appid>\d+)\b")
UINT32_MODULUS = 2**32


@dataclass(frozen=True)
class SteamEvent:
    event_type: str
    event_time: str
    source_appid: str
    appid: str
    raw_line: str
    launch_command: str | None = None


def parse_line(line: str) -> SteamEvent | None:
    """Return a recognized Steam start or stop event, otherwise ``None``."""
    raw_line = line.strip()
    start = START_PATTERN.match(raw_line)
    if start:
        data = start.groupdict()
        return SteamEvent(
            "START",
            data["timestamp"],
            data["appid"],
            canonical_start_appid(data["appid"], data["command"]),
            raw_line,
            data["command"],
        )

    stop = STOP_PATTERN.match(raw_line)
    if stop:
        data = stop.groupdict()
        return SteamEvent(
            "STOP",
            data["timestamp"],
            data["appid"],
            canonical_stop_appid(data["appid"]),
            raw_line,
        )
    return None


def canonical_start_appid(source_appid: str, command: str) -> str:
    """Resolve the AppID Steam uses later in its running-list removal event."""
    launch_appid = STEAM_LAUNCH_APPID_PATTERN.search(command)
    if launch_appid:
        return launch_appid["appid"]

    raw_appid = int(source_appid)
    if raw_appid >= UINT32_MODULUS:
        # Steam encodes some non-Steam shortcuts as a 64-bit process AppID.
        # The matching unsigned 32-bit shortcut AppID is held in its high word.
        return str(raw_appid >> 32)
    return source_appid


def canonical_stop_appid(source_appid: str) -> str:
    """Convert Steam's signed 32-bit running-list AppID to its unsigned form."""
    raw_appid = int(source_appid)
    return str(raw_appid + UINT32_MODULUS if raw_appid < 0 else raw_appid)
