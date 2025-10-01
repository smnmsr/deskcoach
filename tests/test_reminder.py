from types import SimpleNamespace
from datetime import datetime, timedelta
import sys
import types

# Install a minimal dummy PyQt6.QtCore with QObject to satisfy reminder import
qtcore = types.SimpleNamespace(QObject=object)
pyqt6 = types.SimpleNamespace(QtCore=qtcore)
sys.modules.setdefault("PyQt6", pyqt6)
sys.modules.setdefault("PyQt6.QtCore", qtcore)

import deskcoach.services.reminder as reminder


class DummySession:
    def __init__(self, unlocked=True):
        self._unlocked = unlocked

    def is_unlocked(self):
        return self._unlocked


def make_engine(monkeypatch, **cfg_kwargs):
    cfg = SimpleNamespace(
        stand_threshold_mm=900,
        remind_after_minutes=1,
        remind_repeat_minutes=5,
        snooze_minutes=30,
        standing_check_after_minutes=30,
        standing_check_repeat_minutes=30,
    )
    for k, v in cfg_kwargs.items():
        setattr(cfg, k, v)

    sess = DummySession(unlocked=True)

    eng = reminder.ReminderEngine(cfg, sess)
    # Avoid DB access by patching streak calculators
    monkeypatch.setattr(eng, "_compute_seated_streak_minutes", lambda ts, h: 60)
    monkeypatch.setattr(eng, "_compute_standing_streak_minutes", lambda ts, h: 0)
    # Patch notifier to capture calls
    calls = []

    def fake_notify(title, message):
        calls.append((title, message))

    monkeypatch.setattr(reminder.notifier, "notify", fake_notify)
    return eng, calls


def test_snooze_suppresses_notifications(monkeypatch):
    eng, calls = make_engine(monkeypatch, remind_after_minutes=1, remind_repeat_minutes=1)
    eng.snooze(10)
    eng.on_new_measurement(int(datetime.now().timestamp()), 800)  # seated
    assert calls == []


def test_seated_triggers_once_then_cadence(monkeypatch):
    eng, calls = make_engine(monkeypatch, remind_after_minutes=1, remind_repeat_minutes=10)
    ts = int(datetime.now().timestamp())
    eng.on_new_measurement(ts, 800)  # seated below threshold
    assert calls and calls[0][0] == "Stand up"
    # Immediate second call should not notify due to repeat cadence
    eng.on_new_measurement(ts + 5, 800)
    assert len(calls) == 1
    # Manually allow next notification by moving next_ready into the past
    eng._next_ready_seated = datetime.now() - timedelta(seconds=1)
    eng.on_new_measurement(ts + 20, 800)
    assert len(calls) == 2


def test_locked_session_blocks_notifications(monkeypatch):
    eng, calls = make_engine(monkeypatch)
    # Simulate locked by swapping session method
    eng._session.is_unlocked = lambda: False
    eng.on_new_measurement(int(datetime.now().timestamp()), 800)
    assert calls == []


def test_lock_reset_creates_new_timewindow_even_if_later_short_lock(monkeypatch, tmp_path):
    # Use a temp DB
    from deskcoach.models import store as mstore

    dbfile = tmp_path / "deskcoach.db"
    monkeypatch.setattr(mstore, "db_path", lambda: dbfile)
    mstore.init_db()

    # Fixed reference time to avoid flakiness
    base_now = int(datetime(2025, 1, 1, 12, 0, 0).timestamp())

    # One old seated measurement before any locks (simulates no samples while locked)
    mstore.save_measurement(base_now - 5000, 800)  # seated height below threshold

    # A long lock/unlock pair earlier than a later short pair
    # Long pair: 5 minutes lock (meets threshold)
    mstore.save_session_event(base_now - 600, "LOCK")
    mstore.save_session_event(base_now - 300, "UNLOCK")

    # Short pair: 30 seconds lock (below threshold)
    mstore.save_session_event(base_now - 60, "LOCK")
    mstore.save_session_event(base_now - 30, "UNLOCK")

    # Build engine with 5 minute reset threshold
    cfg = SimpleNamespace(stand_threshold_mm=900, lock_reset_threshold_minutes=5)
    sess = DummySession(unlocked=True)
    eng = reminder.ReminderEngine(cfg, sess)

    # Latest height is seated; seated streak should reset at the long UNLOCK (base_now - 300)
    seated_min = eng._compute_seated_streak_minutes(base_now, latest_height=800)
    assert seated_min == 5, f"Expected 5 minutes since last long unlock, got {seated_min}"
