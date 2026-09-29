"""Environment-based runtime configuration and logging setup."""

import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path

DEFAULT_STEAM_LOG_PATH = Path.home() / ".local/share/Steam/logs/gameprocess_log.txt"
DEFAULT_CHECK_INTERVAL = 2.0


@dataclass(frozen=True)
class Config:
    log_file: Path
    db_file: Path
    check_interval: float


def positive_float(value: str, variable_name: str) -> float:
    """Parse a strictly positive environment value."""
    try:
        result = float(value)
    except ValueError as error:
        raise ValueError(f"{variable_name} must be a positive number, got {value!r}.") from error
    if result <= 0:
        raise ValueError(f"{variable_name} must be greater than zero, got {value!r}.")
    return result


def load_config() -> Config:
    """Load configuration from environment variables."""
    log_file = Path(os.getenv("STEAM_LOG_PATH", str(DEFAULT_STEAM_LOG_PATH)))
    data_dir = Path(os.getenv("AGENT_DATA_DIR", "."))
    db_file = Path(os.getenv("AGENT_DB_PATH", str(data_dir / "agent.db")))
    interval = positive_float(os.getenv("CHECK_INTERVAL", str(DEFAULT_CHECK_INTERVAL)), "CHECK_INTERVAL")
    return Config(log_file=log_file, db_file=db_file, check_interval=interval)


def configure_logging() -> None:
    """Configure logs."""
    if hasattr(time, "tzset"):
        time.tzset()
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, None)
    if not isinstance(level, int):
        raise ValueError(f"LOG_LEVEL must be a standard logging level, got {level_name!r}.")
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S %Z",
    )
