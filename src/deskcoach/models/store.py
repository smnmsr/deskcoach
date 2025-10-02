"""SQLite persistence for measurements and session events.

Stores time series of desk height measurements and lock/unlock session events.
Also contains simple daily aggregation helpers for seated/standing durations.
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta, timezone

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
        # Daily aggregates for quick UI stats
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_aggregates (
                date TEXT PRIMARY KEY,                 -- YYYY-MM-DD (local date)
                sitting_sec INTEGER NOT NULL,
                standing_sec INTEGER NOT NULL,
                updated_ts INTEGER NOT NULL           -- last aggregation wall-clock ts
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


# ------------------------ Aggregation helpers ------------------------

def _seconds_since_midnight(ts: int) -> int:
    dt = datetime.fromtimestamp(ts)
    return dt.hour * 3600 + dt.minute * 60 + dt.second


def _day_bounds_local(ts: int | None = None) -> tuple[int, str]:
    """Return start-of-day ts for the local date of ts (or now) and date string.
    Returns (start_ts, date_str).
    """
    base = datetime.fromtimestamp(ts) if ts is not None else datetime.now()
    start = base.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(start.timestamp()), start.strftime("%Y-%m-%d")


def _locked_intervals(start_ts: int, end_ts: int) -> list[tuple[int, int]]:
    """Return list of [lock_start, lock_end) intervals overlapping [start_ts, end_ts].

    This reconstructs lock ranges from session_events, considering the last
    event before the window to determine whether we start locked, and treating
    missing trailing UNLOCK as locked until end_ts.
    """
    if end_ts <= start_ts:
        return []
    intervals: list[tuple[int, int]] = []
    path = db_path()
    try:
        with sqlite3.connect(path) as conn:
            row = conn.execute(
                "SELECT ts, event FROM session_events WHERE ts <= ? ORDER BY ts DESC LIMIT 1",
                (start_ts,),
            ).fetchone()
            start_locked = bool(row and str(row[1]).upper() == "LOCK")
            # Events in window
            cur = conn.execute(
                "SELECT ts, event FROM session_events WHERE ts > ? AND ts <= ? ORDER BY ts ASC",
                (start_ts, end_ts),
            )
            events = [(int(r[0]), str(r[1]).upper()) for r in cur]
    except Exception:
        # On any DB error, assume no locks to avoid undercounting time
        return []

    locked = start_locked
    lock_start: int | None = start_ts if locked else None
    for ts, ev in events:
        if ev == "LOCK":
            if not locked:
                locked = True
                lock_start = max(ts, start_ts)
        elif ev == "UNLOCK":
            if locked and lock_start is not None:
                lock_end = min(ts, end_ts)
                if lock_end > lock_start:
                    intervals.append((lock_start, lock_end))
                locked = False
                lock_start = None
    if locked and lock_start is not None:
        lock_end = end_ts
        if lock_end > lock_start:
            intervals.append((lock_start, lock_end))
    return intervals


def compute_day_aggregates(start_ts: int, end_ts: int, stand_threshold_mm: int) -> tuple[int, int]:
    """Compute seated/standing seconds between [start_ts, end_ts] using samples,
    excluding time while the session is locked.

    Each interval between consecutive samples is attributed to the state of the
    earlier sample; the trailing interval to end_ts uses the last sample's state.
    Locked sub-intervals are removed from attribution.
    """
    if end_ts <= start_ts:
        return 0, 0
    path = db_path()
    seated = 0
    standing = 0
    try:
        with sqlite3.connect(path) as conn:
            cur = conn.execute(
                "SELECT ts, height_mm FROM measurements WHERE ts >= ? AND ts <= ? ORDER BY ts ASC",
                (start_ts, end_ts),
            )
            rows = [(int(r[0]), int(r[1])) for r in cur]
    except Exception:
        rows = []
    if not rows:
        return 0, 0

    # Build lock intervals
    lock_intervals = _locked_intervals(start_ts, end_ts)

    def _overlap_len(a0: int, a1: int, b0: int, b1: int) -> int:
        return max(0, min(a1, b1) - max(a0, b0))

    def _subtract_locked(seg_start: int, seg_end: int) -> int:
        length = max(0, seg_end - seg_start)
        if length == 0 or not lock_intervals:
            return length
        cut = 0
        for l0, l1 in lock_intervals:
            cut += _overlap_len(seg_start, seg_end, l0, l1)
            if cut >= length:
                return 0
        return max(0, length - cut)

    thr = int(stand_threshold_mm)
    # Attribute consecutive sample intervals
    for i in range(len(rows) - 1):
        t0, h0 = rows[i]
        t1, _ = rows[i + 1]
        if t1 <= t0:
            continue
        effective = _subtract_locked(t0, t1)
        if effective <= 0:
            continue
        if h0 >= thr:
            standing += effective
        else:
            seated += effective
    # Tail from last sample to end_ts
    last_ts, last_h = rows[-1]
    if end_ts > last_ts:
        effective = _subtract_locked(last_ts, end_ts)
        if effective > 0:
            if last_h >= thr:
                standing += effective
            else:
                seated += effective
    return seated, standing


def upsert_daily_aggregate(date_str: str, sitting_sec: int, standing_sec: int, updated_ts: int) -> None:
    path = db_path()
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT INTO daily_aggregates(date, sitting_sec, standing_sec, updated_ts)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                sitting_sec=excluded.sitting_sec,
                standing_sec=excluded.standing_sec,
                updated_ts=excluded.updated_ts
            """,
            (date_str, int(sitting_sec), int(standing_sec), int(updated_ts)),
        )
        conn.commit()


def update_daily_aggregates_now(stand_threshold_mm: int, now_ts: int | None = None) -> None:
    """Recompute today's aggregates from midnight until now and upsert."""
    now = int(now_ts if now_ts is not None else datetime.now().timestamp())
    start_ts, date_str = _day_bounds_local(now)
    sitting, standing = compute_day_aggregates(start_ts, now, stand_threshold_mm)
    upsert_daily_aggregate(date_str, sitting, standing, now)


def get_today_aggregates(stand_threshold_mm: int, now_ts: int | None = None) -> tuple[int, int]:
    """Return (sitting_sec, standing_sec) for today, recomputing if needed."""
    now = int(now_ts if now_ts is not None else datetime.now().timestamp())
    start_ts, date_str = _day_bounds_local(now)
    # Try read existing row first
    path = db_path()
    try:
        with sqlite3.connect(path) as conn:
            row = conn.execute(
                "SELECT sitting_sec, standing_sec, updated_ts FROM daily_aggregates WHERE date=?",
                (date_str,),
            ).fetchone()
            if row:
                # If last update earlier than a few minutes, recompute for freshness
                sitting_sec, standing_sec, updated_ts = int(row[0]), int(row[1]), int(row[2])
                if updated_ts >= now - 120:  # 2 minutes freshness window
                    return sitting_sec, standing_sec
    except Exception:
        pass
    # Fallback to recompute
    sitting, standing = compute_day_aggregates(start_ts, now, stand_threshold_mm)
    upsert_daily_aggregate(date_str, sitting, standing, now)
    return sitting, standing


def get_yesterday_aggregates_until_same_time(stand_threshold_mm: int, now_ts: int | None = None) -> tuple[int, int]:
    """Return yesterday's (sitting_sec, standing_sec) up to the same clock time as now."""
    now = int(now_ts if now_ts is not None else datetime.now().timestamp())
    # Determine seconds since midnight for now
    sec_since_midnight = _seconds_since_midnight(now)
    # Compute yesterday's start and end
    today_start_ts, _ = _day_bounds_local(now)
    y_start_ts = today_start_ts - 24 * 3600
    y_end_ts = y_start_ts + sec_since_midnight
    return compute_day_aggregates(y_start_ts, y_end_ts, stand_threshold_mm)
