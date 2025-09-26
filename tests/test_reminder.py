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
