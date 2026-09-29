"""Incremental, rotation-aware reader for Steam's gameprocess log."""

import logging

from config import Config
from database import database, get_meta, set_meta
from sessions import process_event
from steam_log import parse_line

logger = logging.getLogger("steam_playtime")


def read_logs(config: Config) -> None:
    """Read complete appended lines and atomically store their processing state."""
    if not config.log_file.exists():
        logger.warning("log.not_found             | path=%s", config.log_file)
        return

    stat = config.log_file.stat()
    current_size = stat.st_size
    current_inode = str(stat.st_ino)
    with database(config.db_file) as conn:
        stored_offset = int(get_meta(conn, "log_offset") or "0")
        stored_inode = get_meta(conn, "log_inode")
        if stored_inode != current_inode or current_size < stored_offset:
            logger.info("log.rotation_detected     | action=reset_offset")
            stored_offset = 0
            set_meta(conn, "log_inode", current_inode)

    if stored_offset == current_size:
        return

    with config.log_file.open("r", encoding="utf-8", errors="ignore") as log_file:
        log_file.seek(stored_offset)
        while line := log_file.readline():
            if not line.endswith("\n"):
                logger.debug("log.incomplete_line       | action=defer")
                break
            next_offset = log_file.tell()
            event = parse_line(line)
            with database(config.db_file) as conn:
                if event:
                    process_event(conn, event, current_inode, stored_offset)
                set_meta(conn, "log_inode", current_inode)
                set_meta(conn, "log_offset", str(next_offset))
            stored_offset = next_offset
