"""Session persistence rules and ingestion-event audit trail."""

import logging
import sqlite3
from datetime import datetime

from steam_log import SteamEvent

TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"
logger = logging.getLogger("steam_playtime")


def close_session(conn: sqlite3.Connection, session: sqlite3.Row, end_time: str) -> float:
    """Mark a running session as completed and return its duration."""
    start = datetime.strptime(session["start_time"], TIMESTAMP_FORMAT)
    end = datetime.strptime(end_time, TIMESTAMP_FORMAT)
    duration = max(0.0, (end - start).total_seconds())
    conn.execute(
        "UPDATE sessions SET end_time = ?, duration_seconds = ?, status = 'COMPLETED' WHERE id = ?",
        (end_time, duration, session["id"]),
    )
    return duration


def record_event(conn: sqlite3.Connection, event: SteamEvent, inode: str, offset: int) -> int | None:
    """Record a source event once and return its id, or None when already seen."""
    cursor = conn.execute(
        "INSERT OR IGNORE INTO ingested_events "
        "(source_inode, source_offset, event_type, event_time, appid, launch_command, raw_line) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (inode, offset, event.event_type, event.event_time, event.appid, event.launch_command, event.raw_line),
    )
    return cursor.lastrowid if cursor.rowcount else None


def link_event_to_session(conn: sqlite3.Connection, event_id: int, session_id: int | None) -> None:
    """Associate an ingested source event with the affected session."""
    # TODO: Add exception if session_id is None
    conn.execute("UPDATE ingested_events SET session_id = ? WHERE id = ?", (session_id, event_id))


def process_event(conn: sqlite3.Connection, event: SteamEvent, inode: str, offset: int) -> None:
    """Persist an event and apply its session-state transition exactly once."""
    event_id = record_event(conn, event, inode, offset)
    if event_id is None:
        logger.debug("event.duplicate           | inode=%s offset=%s", inode, offset)
        return

    if event.event_type == "START":
        previous = conn.execute(
            "SELECT id, start_time FROM sessions WHERE appid = ? AND status = 'RUNNING' ORDER BY id DESC LIMIT 1",
            (event.appid,),
        ).fetchone()
        if previous:
            duration = close_session(conn, previous, event.event_time)
            logger.warning(
                "session.recovered         | id=%s appid=%s duration=%.0fs",
                previous["id"], event.appid, duration,
            )

        cursor = conn.execute(
            "INSERT INTO sessions (appid, launch_command, start_time, status) VALUES (?, ?, ?, 'RUNNING')",
            (event.appid, event.launch_command, event.event_time),
        )
        link_event_to_session(conn, event_id, cursor.lastrowid)
        logger.info("session.started           | appid=%s start=%s", event.appid, event.event_time)
        return

    running = conn.execute(
        "SELECT id, start_time FROM sessions WHERE appid = ? AND status = 'RUNNING' ORDER BY id DESC LIMIT 1",
        (event.appid,),
    ).fetchone()
    if not running:
        logger.warning("session.unmatched_end     | appid=%s", event.appid)
        return
    duration = close_session(conn, running, event.event_time)
    link_event_to_session(conn, event_id, running["id"])
    logger.info(
        "session.completed         | id=%s appid=%s duration=%.0fs",
        running["id"], event.appid, duration,
    )
