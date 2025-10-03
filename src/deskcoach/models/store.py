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

    Delegates time attribution to utils.time_stats.accumulate_sit_stand_seconds
    to keep separation of concerns (DB I/O vs. time math).
    """
    if end_ts <= start_ts:
        return 0, 0
    path = db_path()
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

    # Delegate to utility function
    try:
        from ..utils.time_stats import accumulate_sit_stand_seconds
    except Exception:  # pragma: no cover - fallback for absolute import usage
        from deskcoach.utils.time_stats import accumulate_sit_stand_seconds  # type: ignore

    seated, standing = accumulate_sit_stand_seconds(
        measurements=rows,
        lock_intervals=lock_intervals,
        stand_threshold_mm=int(stand_threshold_mm),
        end_ts=int(end_ts),
    )
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
    """Return yesterday's (sitting_sec, standing_sec) up to the same clock time as now.

    Notes
    -----
    This function computes the values on-the-fly from raw measurement samples
    and session lock/unlock events for the window:
      [yesterday 00:00:00 local, yesterday 00:00:00 + seconds_since_midnight(now)).
    It intentionally does not read from the ``daily_aggregates`` table. By
    design we only upsert today's aggregate row for quick UI reads; comparing
    to yesterday uses direct computation so you may not see a ``daily_aggregates``
    entry for yesterday. That is expected.
    """
    now = int(now_ts if now_ts is not None else datetime.now().timestamp())
    # Determine seconds since midnight for now
    sec_since_midnight = _seconds_since_midnight(now)
    # Compute yesterday's start and end
    today_start_ts, _ = _day_bounds_local(now)
    y_start_ts = today_start_ts - 24 * 3600
    y_end_ts = y_start_ts + sec_since_midnight
    return compute_day_aggregates(y_start_ts, y_end_ts, stand_threshold_mm)



def _day_bounds_for_date_str(date_str: str) -> tuple[int, int]:
    """Return (start_ts, end_ts) for the given local date string YYYY-MM-DD."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
    except Exception:
        # Fallback to today
        start_ts, _ = _day_bounds_local(None)
        return start_ts, start_ts + 24 * 3600
    start = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    start_ts = int(start.timestamp())
    return start_ts, start_ts + 24 * 3600


def compute_full_day_aggregates_for_date(date_str: str, stand_threshold_mm: int) -> tuple[int, int]:
    """Compute seated/standing seconds for the full local day given by date_str."""
    start_ts, end_ts = _day_bounds_for_date_str(date_str)
    return compute_day_aggregates(start_ts, end_ts, stand_threshold_mm)


def get_aggregate_for_date(date_str: str) -> tuple[int, int] | None:
    """Return (sitting_sec, standing_sec) for date if present in daily_aggregates."""
    path = db_path()
    try:
        with sqlite3.connect(path) as conn:
            row = conn.execute(
                "SELECT sitting_sec, standing_sec FROM daily_aggregates WHERE date=?",
                (date_str,),
            ).fetchone()
            if row:
                return int(row[0]), int(row[1])
    except Exception:
        pass
    return None


essentially_no_data_sentinel = (-1, -1)  # internal use to mark no compute


def ensure_daily_aggregate(date_str: str, stand_threshold_mm: int) -> tuple[int, int]:
    """Ensure daily_aggregates has a row for date_str; compute and upsert if missing.
    Returns (sitting_sec, standing_sec).
    """
    existing = get_aggregate_for_date(date_str)
    if existing is not None:
        return existing
    # Compute once and persist
    sitting, standing = compute_full_day_aggregates_for_date(date_str, stand_threshold_mm)
    try:
        now_ts = int(datetime.now().timestamp())
        upsert_daily_aggregate(date_str, sitting, standing, now_ts)
    except Exception:
        pass
    return sitting, standing


def get_yesterday_full_aggregate(stand_threshold_mm: int, now_ts: int | None = None) -> tuple[int, int]:
    """Return full-day (sitting_sec, standing_sec) for yesterday, ensuring it's cached."""
    now = int(now_ts if now_ts is not None else datetime.now().timestamp())
    today_start_ts, today_str = _day_bounds_local(now)
    # Compute yesterday's date string
    y_dt = datetime.fromtimestamp(today_start_ts) - timedelta(days=1)
    y_str = y_dt.strftime("%Y-%m-%d")
    return ensure_daily_aggregate(y_str, stand_threshold_mm)


def backfill_past_aggregates(stand_threshold_mm: int, upto_now_ts: int | None = None) -> None:
    """Backfill daily_aggregates for all full past days based on measurements.

    - Finds the first measurement timestamp and iterates through each local date
      up to yesterday, computing and inserting missing aggregates.
    - Skips days that already have an entry.
    """
    now = int(upto_now_ts if upto_now_ts is not None else datetime.now().timestamp())
    path = db_path()
    first_ts: int | None = None
    try:
        with sqlite3.connect(path) as conn:
            row = conn.execute("SELECT MIN(ts) FROM measurements").fetchone()
            if row and row[0] is not None:
                first_ts = int(row[0])
    except Exception:
        first_ts = None
    if first_ts is None:
        return  # nothing to backfill
    # Start from local date of first_ts
    start_of_first, _ = _day_bounds_local(first_ts)
    start_dt = datetime.fromtimestamp(start_of_first)
    today_start_ts, _ = _day_bounds_local(now)
    # Iterate day by day until yesterday
    cur_dt = start_dt
    yesterday_dt = datetime.fromtimestamp(today_start_ts) - timedelta(days=1)
    try:
        with sqlite3.connect(path) as conn:
            while cur_dt <= yesterday_dt:
                ds = cur_dt.strftime("%Y-%m-%d")
                # Skip if exists
                row = conn.execute("SELECT 1 FROM daily_aggregates WHERE date=?", (ds,)).fetchone()
                if not row:
                    s, t = compute_full_day_aggregates_for_date(ds, stand_threshold_mm)
                    upsert_daily_aggregate(ds, s, t, int(now))
                cur_dt = cur_dt + timedelta(days=1)
    except Exception:
        # Best-effort; ignore failures to avoid blocking UI
        return


def clear_daily_aggregates() -> None:
    """Delete all rows from daily_aggregates.

    This is used when the user requests a full recomputation of aggregates.
    """
    path = db_path()
    try:
        with sqlite3.connect(path) as conn:
            conn.execute("DELETE FROM daily_aggregates")
            conn.commit()
    except Exception:
        # Non-fatal; caller may attempt to backfill anyway
        return
