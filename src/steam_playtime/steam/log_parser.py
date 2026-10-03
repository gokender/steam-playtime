"""Parse relevant events from Steam's gameprocess log."""

import re

from steam_playtime.models import SteamEvent

START = re.compile(r'^\[(?P<time>[^]]+)\] AppID (?P<appid>\d+) adding PID \d+ as a tracked process "(?P<command>.*)"$')
STOP = re.compile(r"^\[(?P<time>[^]]+)\] Remove (?P<appid>-?\d+) from running list$")
LAUNCH_APPID = re.compile(r"\bSteamLaunch AppId=(?P<appid>\d+)\b")
UINT32 = 2**32


def parse_line(line: str) -> SteamEvent | None:
    raw = line.strip()
    start = START.match(raw)
    if start:
        source_appid = start["appid"]
        command = start["command"]
        launch_appid = LAUNCH_APPID.search(command)
        appid = launch_appid["appid"] if launch_appid else str(int(source_appid) >> 32) if int(source_appid) >= UINT32 else source_appid
        return SteamEvent("START", start["time"], source_appid, appid, raw, command)
    stop = STOP.match(raw)
    if stop:
        source_appid = stop["appid"]
        appid = str(int(source_appid) + UINT32 if int(source_appid) < 0 else int(source_appid))
        return SteamEvent("STOP", stop["time"], source_appid, appid, raw)
    return None
