"""Entrypoint for the local Steam play-session collector."""

import logging
import signal
import time

from config import configure_logging, load_config
from database import init_db
from log_reader import read_logs

logger = logging.getLogger("steam_playtime")
stop_requested = False


def request_stop(signum: int, _frame: object) -> None:
    """Request a clean shutdown after a container or terminal signal."""
    global stop_requested
    logger.info("agent.stop_requested      | signal=%s", signum)
    stop_requested = True


def main() -> None:
    configure_logging()
    try:
        config = load_config()
    except ValueError as error:
        logger.error("configuration.invalid    | error=%s", error)
        raise SystemExit(2) from error

    init_db(config.db_file)
    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    logger.info(
        "agent.started             | log_path=%s db_path=%s interval=%.2fs",
        config.log_file,
        config.db_file,
        config.check_interval,
    )
    while not stop_requested:
        try:
            read_logs(config)
        except OSError as error:
            logger.exception("log.read_failed          | error=%s", error)
        time.sleep(config.check_interval)
    logger.info("agent.stopped")


if __name__ == "__main__":
    main()
