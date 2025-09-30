from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from PyQt6.QtCore import QObject

try:
    # relative import when used as package within services
    from ..models import store
    from . import notifier
except Exception:  # pragma: no cover
    from deskcoach.models import store  # type: ignore
    from deskcoach.services import notifier  # type: ignore

log = logging.getLogger(__name__)


@dataclass
class ReminderConfig:
    stand_threshold_mm: int
    remind_after_minutes: int
    remind_repeat_minutes: int
    snooze_minutes: int
    standing_check_after_minutes: int
    standing_check_repeat_minutes: int
    lock_reset_threshold_minutes: int


class ReminderEngine(QObject):
    """Reminder logic driven by new measurements.

    Call on_new_measurement(ts, height_mm) after each saved measurement.
    """

    def __init__(self, cfg: object, session_watcher: object) -> None:
        super().__init__()
        # Pull values from cfg (SimpleNamespace-like)
        self.cfg = ReminderConfig(
            stand_threshold_mm=int(getattr(cfg, "stand_threshold_mm", 900)),
            remind_after_minutes=int(getattr(cfg, "remind_after_minutes", 45)),
            remind_repeat_minutes=int(getattr(cfg, "remind_repeat_minutes", 5)),
            snooze_minutes=int(getattr(cfg, "snooze_minutes", 30)),
            standing_check_after_minutes=int(getattr(cfg, "standing_check_after_minutes", 30)),
            standing_check_repeat_minutes=int(getattr(cfg, "standing_check_repeat_minutes", 30)),
            lock_reset_threshold_minutes=int(getattr(cfg, "lock_reset_threshold_minutes", 5)),
        )
        self._snoozed_until: Optional[datetime] = None
        self._next_ready_at: Optional[datetime] = None
        # Separate cadence for standing-checks
        self._next_ready_standing: Optional[datetime] = None
        self._next_ready_seated: Optional[datetime] = None
        self._session = session_watcher
        self._lock_started_at: Optional[datetime] = None
        # Connect to lock/unlock to pause countdowns
        try:
            session_watcher.session_locked.connect(self._on_locked)  # type: ignore[attr-defined]
            session_watcher.session_unlocked.connect(self._on_unlocked)  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover
            pass

    def is_snoozed(self) -> bool:
        if self._snoozed_until is None:
            return False
        return datetime.now() < self._snoozed_until

    def snooze(self, minutes: Optional[int] = None) -> None:
        mins = int(minutes if minutes is not None else self.cfg.snooze_minutes)
        self._snoozed_until = datetime.now() + timedelta(minutes=mins)
        log.info("Snoozed reminders for %s minutes (until %s)", mins, self._snoozed_until.strftime("%H:%M"))

    # Lock handling: pause countdowns while locked
    def _on_locked(self) -> None:
        self._lock_started_at = datetime.now()

    def _on_unlocked(self) -> None:
        if self._lock_started_at is None:
            return
        delta = datetime.now() - self._lock_started_at
        self._lock_started_at = None
        # Extend snooze and next_ready by lock duration to effectively pause them
        if self._snoozed_until is not None:
            self._snoozed_until += delta
        if self._next_ready_at is not None:
            self._next_ready_at += delta
        if self._next_ready_standing is not None:
            self._next_ready_standing += delta
        if self._next_ready_seated is not None:
            self._next_ready_seated += delta

    def _db_conn(self) -> sqlite3.Connection:
        path = store.db_path()  # type: ignore[attr-defined]
        return sqlite3.connect(path)

    def _last_long_lock_unlock_ts(self, threshold_minutes: int) -> Optional[int]:
        """Return the ts of the most recent UNLOCK that followed a LOCK lasting >= threshold.

        If no such pair exists, return None.
        """
        threshold_sec = int(max(0, threshold_minutes)) * 60
        try:
            with self._db_conn() as conn:
                row = conn.execute(
                    "SELECT ts FROM session_events WHERE event='UNLOCK' ORDER BY ts DESC LIMIT 1"
                ).fetchone()
                if not row:
                    return None
                unlock_ts = int(row[0])
                row2 = conn.execute(
                    "SELECT ts FROM session_events WHERE event='LOCK' AND ts <= ? ORDER BY ts DESC LIMIT 1",
                    (unlock_ts,),
                ).fetchone()
                if not row2:
                    return None
                lock_ts = int(row2[0])
                if unlock_ts - lock_ts >= threshold_sec:
                    return unlock_ts
        except Exception as e:  # pragma: no cover - defensive
            log.debug("DB session_events query failed: %s", e)
        return None

    def _compute_seated_streak_minutes(self, now_ts: int, latest_height: int) -> int:
        threshold = self.cfg.stand_threshold_mm
        if latest_height >= threshold:
            return 0
        last_ts = now_ts
        # Walk backwards until we hit a standing sample
        try:
            with self._db_conn() as conn:
                cur = conn.execute(
                    "SELECT ts, height_mm FROM measurements ORDER BY ts DESC LIMIT 1000"
                )
                for row in cur:
                    ts, height_mm = int(row[0]), int(row[1])
                    if height_mm >= threshold:
                        # Found standing sample boundary
                        break
                    last_ts = ts
        except Exception as e:  # pragma: no cover - don't break app on DB issues
            log.debug("DB streak query failed: %s", e)
        # Apply lock reset threshold: if there was a long lock, streak can't start before last unlock
        try:
            lu_ts = self._last_long_lock_unlock_ts(self.cfg.lock_reset_threshold_minutes)
            if lu_ts is not None and lu_ts > last_ts:
                last_ts = lu_ts
        except Exception:
            pass
        streak_sec = max(0, now_ts - last_ts)
        return streak_sec // 60

    def _compute_standing_streak_minutes(self, now_ts: int, latest_height: int) -> int:
        threshold = self.cfg.stand_threshold_mm
        if latest_height < threshold:
            return 0
        last_ts = now_ts
        try:
            with self._db_conn() as conn:
                cur = conn.execute(
                    "SELECT ts, height_mm FROM measurements ORDER BY ts DESC LIMIT 1000"
                )
                for row in cur:
                    ts, height_mm = int(row[0]), int(row[1])
                    if height_mm < threshold:
                        # Found seated sample boundary
                        break
                    last_ts = ts
        except Exception as e:
            log.debug("DB standing streak query failed: %s", e)
        # Apply lock reset threshold: if there was a long lock, streak can't start before last unlock
        try:
            lu_ts = self._last_long_lock_unlock_ts(self.cfg.lock_reset_threshold_minutes)
            if lu_ts is not None and lu_ts > last_ts:
                last_ts = lu_ts
        except Exception:
            pass
        streak_sec = max(0, now_ts - last_ts)
        return streak_sec // 60

    def on_new_measurement(self, ts: int, height_mm: int) -> None:
        """Evaluate reminder conditions upon receiving a new measurement.
        ts is expected to be an integer unix timestamp (seconds).
        """
        try:
            # Never notify when locked
            try:
                unlocked = bool(self._session.is_unlocked())  # type: ignore[attr-defined]
            except Exception:
                unlocked = True
            if not unlocked:
                return

            threshold = self.cfg.stand_threshold_mm
            seated_streak_min = self._compute_seated_streak_minutes(ts, height_mm)
            standing_streak_min = self._compute_standing_streak_minutes(ts, height_mm)
            is_standing = height_mm >= threshold

            # Reset cadence when switching posture
            if is_standing:
                self._next_ready_seated = None
                self._next_ready_at = None
            else:
                self._next_ready_standing = None
                self._next_ready_at = None

            if self.is_snoozed():
                return

            now = datetime.now()

            # Seated too long -> remind to stand up
            if not is_standing and seated_streak_min >= self.cfg.remind_after_minutes:
                if self._next_ready_seated is None or now >= self._next_ready_seated:
                    try:
                        notifier.notify("Stand up", f"You've been seated for {seated_streak_min} min.")
                    except Exception as e:  # pragma: no cover - ensure no crash
                        log.debug("notify() failed: %s", e)
                    self._next_ready_seated = now + timedelta(minutes=self.cfg.remind_repeat_minutes)

            # Standing for a long time -> posture check
            if is_standing and standing_streak_min >= self.cfg.standing_check_after_minutes:
                if self._next_ready_standing is None or now >= self._next_ready_standing:
                    try:
                        notifier.notify(
                            "Posture check",
                            "You've been standing for a while. Are you still in a good standing position, or slipping into a protective posture?",
                        )
                    except Exception as e:  # pragma: no cover - ensure no crash
                        log.debug("notify() failed: %s", e)
                    self._next_ready_standing = now + timedelta(minutes=self.cfg.standing_check_repeat_minutes)
        except Exception as e:  # pragma: no cover - defensive
            log.debug("ReminderEngine error: %s", e)
