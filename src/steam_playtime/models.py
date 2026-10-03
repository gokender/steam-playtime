"""Shared domain models."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SteamEvent:
    event_type: str
    timestamp: str
    source_appid: str
    appid: str
    raw_line: str
    launch_command: str | None = None


@dataclass(frozen=True)
class GameDetails:
    name: str
    launch_kind: str
    title_source: str
    launch_target: str | None = None
