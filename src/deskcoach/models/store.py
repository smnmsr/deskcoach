"""SQLite persistence for measurements and session events.

Stores time series of desk height measurements and lock/unlock session events.
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

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
        # Measurements table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS measurements (
                ts INTEGER NOT NULL,
                height_mm INTEGER NOT NULL
            )
            """
        )
        # Session events table: event is 'LOCK' or 'UNLOCK'
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS session_events (
                ts INTEGER NOT NULL,
                event TEXT NOT NULL CHECK (event IN ('LOCK','UNLOCK'))
            )
            """
        )
        # Helpful index for recent queries
        conn.execute("CREATE INDEX IF NOT EXISTS idx_session_events_ts ON session_events(ts)")
        conn.commit()
    finally:
        conn.close()
    if existed:
        log.info("Found existing database at %s", path)
    else:
        log.info("Created new database at %s", path)
    return path


_essql = "INSERT INTO measurements(ts, height_mm) VALUES (?, ?)"
_sesql = "INSERT INTO session_events(ts, event) VALUES (?, ?)"


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
        conn.execute(_essql, (ts, height_mm))
        conn.commit()
    log.debug("Saved measurement ts=%s height_mm=%s", ts, height_mm)


def save_session_event(ts: int, event: str) -> None:
    """Persist a session event ('LOCK' or 'UNLOCK')."""
    ev = event.upper()
    if ev not in ("LOCK", "UNLOCK"):
        raise ValueError(f"Invalid session event: {event}")
    path = db_path()
    try:
        with sqlite3.connect(path) as conn:
            conn.execute(_sesql, (ts, ev))
            conn.commit()
        log.debug("Saved session event ts=%s event=%s", ts, ev)
    except Exception as e:  # pragma: no cover - defensive
        log.debug("Failed to save session event: %s", e)
