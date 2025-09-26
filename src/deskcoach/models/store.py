"""SQLite persistence for measurements.

Stores time series of desk height measurements.
"""
from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import Tuple

from platformdirs import PlatformDirs

log = logging.getLogger(__name__)

APP_NAME = "DeskCoach"
APP_AUTHOR = "DeskCoach"  # same for Windows; not critical
_DB_FILENAME = "deskcoach.db"


def db_path() -> Path:
    """Public accessor for the database path in the user data directory."""
    dirs = PlatformDirs(appname=APP_NAME, appauthor=APP_AUTHOR, roaming=False)
    data_dir = Path(dirs.user_data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / _DB_FILENAME


def db_exists() -> bool:
    """Return True if the database file already exists."""
    return db_path().exists()


def init_db() -> Path:
    """Initialize database and ensure schema exists. Returns DB path.

    This first checks if an existing DB is present to preserve historical data
    for trends. If not found, it creates a new one and the required schema.
    """
    path = db_path()
    existed = path.exists()
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS measurements (
                ts INTEGER NOT NULL,
                height_mm INTEGER NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()
    if existed:
        log.info("Found existing database at %s", path)
    else:
        log.info("Created new database at %s", path)
    return path


essql = "INSERT INTO measurements(ts, height_mm) VALUES (?, ?)"


def save_measurement(ts: int, height_mm: int) -> None:
    """Insert a measurement row.

    Parameters
    ----------
    ts: int
        Unix timestamp (seconds).
    height_mm: int
        Height in millimeters.
    """
    path = db_path()
    with sqlite3.connect(path) as conn:
        conn.execute(essql, (ts, height_mm))
        conn.commit()
    log.debug("Saved measurement ts=%s height_mm=%s", ts, height_mm)
