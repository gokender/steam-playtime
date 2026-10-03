"""Incremental Steam log collection and local session state transitions."""

import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from steam_playtime.config import Settings
from steam_playtime.models import GameDetails, SteamEvent
from steam_playtime.steam.log_parser import UINT32, parse_line
from steam_playtime.steam.manifests import title_for_appid
from steam_playtime.storage import agent as storage

logger = logging.getLogger(__name__)
missing_log_warning_path: Path | None = None


def default_log_path() -> Path:
    configured = os.getenv("STEAM_LOG_PATH")
    if configured:
        return Path(configured)
    home = Path.home()
    paths = [
        home / ".local/share/Steam/logs/gameprocess_log.txt",
        Path("/home/deck/.local/share/Steam/logs/gameprocess_log.txt"),
        home / ".var/app/com.valvesoftware.Steam/.local/share/Steam/logs/gameprocess_log.txt",
    ]
    return next((path for path in paths if path.exists()), paths[0])


def utc_timestamp(value: str, timezone: str) -> str:
    local = datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo(timezone))
    return local.astimezone(UTC).isoformat().replace("+00:00", "Z")


def game_details(event: SteamEvent) -> GameDetails:
    title = title_for_appid(event.appid)
    if title:
        return GameDetails(title, "STEAM_APP", "LOCAL_MANIFEST")
    if int(event.source_appid) >= UINT32:
        return GameDetails(f"Non-Steam shortcut {event.appid}", "NON_STEAM_SHORTCUT", "FALLBACK")
    return GameDetails(f"AppID {event.appid}", "UNKNOWN", "FALLBACK")


def collect_once(settings: Settings, log_path: Path | None = None) -> int:
    """Process complete appended log lines, safely resuming by inode and offset."""
    path = log_path or default_log_path()
    global missing_log_warning_path
    if not path.exists():
        if missing_log_warning_path != path:
            logger.warning("Steam log not found: %s", path)
            missing_log_warning_path = path
        return 0
    if missing_log_warning_path == path:
        logger.info("agent | steam_log_found | path=%s", path)
        missing_log_warning_path = None
    stat = path.stat()
    inode = str(stat.st_ino)
    with storage.connection(settings.agent_db) as database:
        offset = int(storage.metadata(database, "log_offset") or "0")
        if storage.metadata(database, "log_inode") != inode or stat.st_size < offset:
            offset = 0
        storage.set_metadata(database, "log_inode", inode)
    processed = 0
    with path.open("r", encoding="utf-8", errors="ignore") as log_file:
        log_file.seek(offset)
        while line := log_file.readline():
            if not line.endswith("\n"):
                break
            next_offset = log_file.tell()
            event = parse_line(line)
            with storage.connection(settings.agent_db) as database:
                if event:
                    _process_event(database, event, inode, offset, settings)
                    processed += 1
                storage.set_metadata(database, "log_inode", inode)
                storage.set_metadata(database, "log_offset", str(next_offset))
            offset = next_offset
    return processed


def _process_event(database, event: SteamEvent, inode: str, offset: int, settings: Settings) -> None:
    cursor = database.execute(
        "INSERT OR IGNORE INTO ingested_events (source_inode, source_offset, event_type, raw_line) VALUES (?, ?, ?, ?)",
        (inode, offset, event.event_type, event.raw_line),
    )
    if not cursor.rowcount:
        return
    event_time = utc_timestamp(event.timestamp, settings.timezone)
    if event.event_type == "START":
        previous = database.execute(
            "SELECT * FROM sessions WHERE appid = ? AND status = 'RUNNING' ORDER BY id DESC LIMIT 1", (event.appid,)
        ).fetchone()
        if previous:
            storage.close_running_session(database, previous, event_time)
        game = game_details(event)
        session = database.execute(
            "INSERT INTO sessions (device_id, appid, launch_command, launch_target, game_name, launch_kind, title_source, start_time, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'RUNNING')",
            (settings.device_id, event.appid, event.launch_command or "", game.launch_target, game.name,
             game.launch_kind, game.title_source, event_time),
        )
        database.execute("UPDATE ingested_events SET session_id = ? WHERE id = ?", (session.lastrowid, cursor.lastrowid))
        logger.info("agent | session_started | game=%s", game.name)
        return
    running = database.execute(
        "SELECT * FROM sessions WHERE appid = ? AND status = 'RUNNING' ORDER BY id DESC LIMIT 1", (event.appid,)
    ).fetchone()
    if running:
        duration = storage.close_running_session(database, running, event_time)
        database.execute("UPDATE ingested_events SET session_id = ? WHERE id = ?", (running["id"], cursor.lastrowid))
        logger.info("agent | session_completed | game=%s duration=%.0fs", running["game_name"], duration)
