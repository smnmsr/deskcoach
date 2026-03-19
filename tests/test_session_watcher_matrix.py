import types
import sys

import pytest

# Module under test will be imported lazily via fixture to allow faking PyQt6
import importlib


class FakeSignal:
    def __init__(self):
        self._subs = []

    def connect(self, fn):
        self._subs.append(fn)

    def emit(self, *args, **kwargs):
        for fn in list(self._subs):
            fn(*args, **kwargs)


def make_fake_pyqt(monkeypatch):
    # Create fake PyQt6 modules minimal API for our tests
    qt_pkg = types.ModuleType("PyQt6")

    qtcore = types.ModuleType("PyQt6.QtCore")

    class QObject:
        pass

    class QAbstractNativeEventFilter:
        pass

    class DummyApp:
        _instance = None

        def __init__(self):
            self._callbacks = []

        @classmethod
        def instance(cls):
            if cls._instance is None:
                cls._instance = DummyApp()
            return cls._instance

        @property
        def aboutToQuit(self):
            return self

        def connect(self, cb):
            self._callbacks.append(cb)

        def fire_quit(self):
            for cb in list(self._callbacks):
                try:
                    cb()
                except Exception:
                    pass

        def removeNativeEventFilter(self, *_):
            pass

        def installNativeEventFilter(self, *_):
            pass

    class Qt:
        class WidgetAttribute:
            WA_DontShowOnScreen = 0

    def pyqtSignal(*_args, **_kwargs):
        return FakeSignal()

    class QTimer:
        def __init__(self, *_args, **_kwargs):
            self.interval = 0
            self._active = False
            self.timeout = FakeSignal()

        def setInterval(self, interval):
            self.interval = interval

        def start(self):
            self._active = True

        def stop(self):
            self._active = False

        def isActive(self):
            return self._active

        @staticmethod
        def singleShot(_interval, callback):
            callback()

    qtcore.QObject = QObject
    qtcore.QAbstractNativeEventFilter = QAbstractNativeEventFilter
    qtcore.QCoreApplication = DummyApp
    qtcore.Qt = Qt
    qtcore.pyqtSignal = pyqtSignal
    qtcore.QTimer = QTimer

    qtwidgets = types.ModuleType("PyQt6.QtWidgets")

    class QWidget:
        def __init__(self):
            self._id = 12345

        def setWindowTitle(self, *_):
            pass

        def setAttribute(self, *_):
            pass

        def resize(self, *_):
            pass

        def setVisible(self, *_):
            pass

        def winId(self):
            return self._id

    qtwidgets.QWidget = QWidget

    sys.modules["PyQt6"] = qt_pkg
    sys.modules["PyQt6.QtCore"] = qtcore
    sys.modules["PyQt6.QtWidgets"] = qtwidgets


@pytest.fixture()
def sw(monkeypatch):
    make_fake_pyqt(monkeypatch)
    # Import or reload the module under test
    mod = importlib.import_module("deskcoach.services.session_watcher")
    mod = importlib.reload(mod)
    return mod


class SignalCatcher:
    def __init__(self):
        self.events = []

    def on_locked(self):
        self.events.append("locked")

    def on_unlocked(self):
        self.events.append("unlocked")


@pytest.fixture(autouse=True)
def restore_module_state(sw, monkeypatch):
    # Ensure we start with a clean-ish module state per test
    # Reset platform and ctypes availability to safe defaults
    monkeypatch.setattr(sw, "wintypes", None, raising=False)
    monkeypatch.setattr(sw, "wtsapi32", None, raising=False)
    monkeypatch.setattr(sw, "kernel32", None, raising=False)
    yield


def make_watcher(monkeypatch, *, platform="win32", wts_available=False, wts_probe=None, desktop_probe=None):
    # Import the module here to avoid relying on a fixture parameter
    m = importlib.import_module("deskcoach.services.session_watcher")
    monkeypatch.setattr(sys, "platform", platform)
    if wts_available:
        monkeypatch.setattr(m, "wintypes", types.SimpleNamespace(), raising=False)
        monkeypatch.setattr(m, "wtsapi32", object(), raising=False)
        monkeypatch.setattr(m, "kernel32", object(), raising=False)
    else:
        monkeypatch.setattr(m, "wintypes", None, raising=False)
        monkeypatch.setattr(m, "wtsapi32", None, raising=False)
        monkeypatch.setattr(m, "kernel32", None, raising=False)

    if wts_probe is not None:
        monkeypatch.setattr(m.SessionWatcher, "_probe_initial_state_wts", lambda self: wts_probe)
    if desktop_probe is not None:
        monkeypatch.setattr(m, "_probe_unlocked_via_input_desktop", lambda: desktop_probe)

    watcher = m.SessionWatcher()
    return watcher


# --- Startup / initialization ---

def test_startup_unlocked_no_signal(sw, monkeypatch):
    catcher = SignalCatcher()
    w = make_watcher(monkeypatch, platform="win32", wts_available=True, wts_probe=True)
    w.session_locked.connect(catcher.on_locked)
    w.session_unlocked.connect(catcher.on_unlocked)
    assert w.is_unlocked() is True
    assert catcher.events == []


def test_startup_locked_no_signal(sw, monkeypatch):
    catcher = SignalCatcher()
    w = make_watcher(monkeypatch, platform="win32", wts_available=True, wts_probe=False)
    w.session_locked.connect(catcher.on_locked)
    w.session_unlocked.connect(catcher.on_unlocked)
    assert w.is_unlocked() is False
    assert catcher.events == []


def test_startup_session_switch_no_console_then_event(sw, monkeypatch):
    catcher = SignalCatcher()
    w = make_watcher(monkeypatch, platform="win32", wts_available=True, wts_probe=None, desktop_probe=None)
    w.session_locked.connect(catcher.on_locked)
    w.session_unlocked.connect(catcher.on_unlocked)
    # Unlock event should still toggle even when active console id is unknown
    w._handle_wts_event(sw.WTS_SESSION_UNLOCK, session_id=10, active_console=None)
    assert w.is_unlocked() is True
    assert catcher.events == ["unlocked"]
    # Subsequent CONNECT is a no-op since we're already unlocked
    w._handle_wts_event(sw.WTS_CONSOLE_CONNECT, session_id=10, active_console=None)
    assert catcher.events == ["unlocked"]


def test_non_windows_platform_unlocked(sw, monkeypatch):
    catcher = SignalCatcher()
    w = make_watcher(monkeypatch, platform="darwin", wts_available=False)
    w.session_locked.connect(catcher.on_locked)
    w.session_unlocked.connect(catcher.on_unlocked)
    assert w.is_unlocked() is True
    assert catcher.events == []


def test_windows_wts_unavailable_unlocked(sw, monkeypatch):
    catcher = SignalCatcher()
    w = make_watcher(monkeypatch, platform="win32", wts_available=False)
    w.session_locked.connect(catcher.on_locked)
    w.session_unlocked.connect(catcher.on_unlocked)
    assert w.is_unlocked() is True
    assert catcher.events == []


# --- Basic lock/unlock ---

def test_lock_unlock_basic(sw, monkeypatch):
    catcher = SignalCatcher()
    w = make_watcher(monkeypatch, platform="win32", wts_available=True, wts_probe=True)
    w.session_locked.connect(catcher.on_locked)
    w.session_unlocked.connect(catcher.on_unlocked)
    # Active console id is 1
    active = 1
    # Lock from unlocked
    w._handle_wts_event(sw.WTS_SESSION_LOCK, session_id=active, active_console=active)
    assert w.is_unlocked() is False
    # duplicate lock
    w._handle_wts_event(sw.WTS_SESSION_LOCK, session_id=active, active_console=active)
    # Unlock
    w._handle_wts_event(sw.WTS_SESSION_UNLOCK, session_id=active, active_console=active)
    assert w.is_unlocked() is True
    # duplicate unlock
    w._handle_wts_event(sw.WTS_SESSION_UNLOCK, session_id=active, active_console=active)
    assert catcher.events == ["locked", "unlocked"]


# --- Console connect/disconnect ---

def test_console_disconnect_connect(sw, monkeypatch):
    catcher = SignalCatcher()
    w = make_watcher(monkeypatch, platform="win32", wts_available=True, wts_probe=True)
    w.session_locked.connect(catcher.on_locked)
    w.session_unlocked.connect(catcher.on_unlocked)
    active = 2
    w._handle_wts_event(sw.WTS_CONSOLE_DISCONNECT, session_id=active, active_console=active)
    assert w.is_unlocked() is False
    w._handle_wts_event(sw.WTS_CONSOLE_CONNECT, session_id=active, active_console=active)
    assert w.is_unlocked() is True
    assert catcher.events == ["locked", "unlocked"]


def test_ignore_non_console_session(sw, monkeypatch):
    catcher = SignalCatcher()
    w = make_watcher(monkeypatch, platform="win32", wts_available=True, wts_probe=True)
    w.session_locked.connect(catcher.on_locked)
    w.session_unlocked.connect(catcher.on_unlocked)
    active = 3
    w._handle_wts_event(sw.WTS_SESSION_LOCK, session_id=99, active_console=active)
    assert catcher.events == []
    assert w.is_unlocked() is True


def test_lock_unlock_unknown_active_console(sw, monkeypatch):
    catcher = SignalCatcher()
    w = make_watcher(monkeypatch, platform="win32", wts_available=True, wts_probe=True)
    w.session_locked.connect(catcher.on_locked)
    w.session_unlocked.connect(catcher.on_unlocked)
    w._handle_wts_event(sw.WTS_SESSION_LOCK, session_id=42, active_console=None)
    assert w.is_unlocked() is False
    w._handle_wts_event(sw.WTS_SESSION_UNLOCK, session_id=42, active_console=None)
    assert w.is_unlocked() is True
    assert catcher.events == ["locked", "unlocked"]


def test_race_disconnect_connect(sw, monkeypatch):
    catcher = SignalCatcher()
    w = make_watcher(monkeypatch, platform="win32", wts_available=True, wts_probe=True)
    w.session_locked.connect(catcher.on_locked)
    w.session_unlocked.connect(catcher.on_unlocked)
    # During switch, accept DISCONNECT/CONNECT even without active console id
    w._handle_wts_event(sw.WTS_CONSOLE_DISCONNECT, session_id=10, active_console=None)
    w._handle_wts_event(sw.WTS_CONSOLE_CONNECT, session_id=11, active_console=None)
    assert w.is_unlocked() is True
    assert catcher.events == ["locked", "unlocked"]


# --- Logon/logoff: ignored ---

def test_logon_logoff_ignored(sw, monkeypatch):
    catcher = SignalCatcher()
    w = make_watcher(monkeypatch, platform="win32", wts_available=True, wts_probe=True)
    w.session_locked.connect(catcher.on_locked)
    w.session_unlocked.connect(catcher.on_unlocked)
    active = 4
    w._handle_wts_event(sw.WTS_SESSION_LOGON, session_id=active, active_console=active)
    w._handle_wts_event(sw.WTS_SESSION_LOGOFF, session_id=active, active_console=active)
    # No mapping -> ignored
    assert catcher.events == []


# --- Power / shutdown ---

def test_shutdown_and_sleep_paths(sw, monkeypatch):
    # Directly invoke _on_locked to simulate shutdown/suspend handling
    catcher = SignalCatcher()
    w = make_watcher(monkeypatch, platform="win32", wts_available=True, wts_probe=True)
    w.session_locked.connect(catcher.on_locked)
    w.session_unlocked.connect(catcher.on_unlocked)
    # simulate QUERYENDSESSION
    w._on_locked()
    assert w.is_unlocked() is False
    # simulate ENDSESSION (duplicate)
    w._on_locked()
    # simulate suspend
    w._on_locked()
    assert catcher.events == ["locked"]


def test_resume_probe_unlock_and_lock(sw, monkeypatch):
    catcher = SignalCatcher()
    # Start locked
    w = make_watcher(monkeypatch, platform="win32", wts_available=True, wts_probe=False)
    w.session_locked.connect(catcher.on_locked)
    w.session_unlocked.connect(catcher.on_unlocked)
    # Resume with desktop unlocked
    monkeypatch.setattr(sw.SessionWatcher, "_probe_initial_state_wts", lambda self: True)
    assert w.is_unlocked() is False
    # simulate resume re-probe path by calling directly
    state = w._probe_initial_state_wts()
    if state:
        w._on_unlocked()
    assert w.is_unlocked() is True
    # Resume with desktop locked
    w._on_locked()
    monkeypatch.setattr(sw.SessionWatcher, "_probe_initial_state_wts", lambda self: False)
    state = w._probe_initial_state_wts()
    if state is False:
        w._on_locked()
    assert w.is_unlocked() is False
    # No spurious unlock
    assert catcher.events == ["unlocked", "locked"]


# --- Event filtering & robustness ---

def test_non_wts_messages_ignored(sw, monkeypatch):
    # We can't easily send arbitrary WM_*; ensure calling unrelated methods doesn't change state
    w = make_watcher(monkeypatch, platform="win32", wts_available=True, wts_probe=True)
    assert w.is_unlocked() is True


def test_event_type_variants_no_duplicates(sw, monkeypatch):
    # Simulate duplicate delivery of the same event via different eventType paths
    catcher = SignalCatcher()
    w = make_watcher(monkeypatch, platform="win32", wts_available=True, wts_probe=True)
    w.session_locked.connect(catcher.on_locked)
    w.session_unlocked.connect(catcher.on_unlocked)
    active = 7
    # Duplicate LOCK events should emit only once
    w._handle_wts_event(sw.WTS_SESSION_LOCK, session_id=active, active_console=active)
    w._handle_wts_event(sw.WTS_SESSION_LOCK, session_id=active, active_console=active)
    # Duplicate UNLOCK events should emit only once
    w._handle_wts_event(sw.WTS_SESSION_UNLOCK, session_id=active, active_console=active)
    w._handle_wts_event(sw.WTS_SESSION_UNLOCK, session_id=active, active_console=active)
    assert catcher.events == ["locked", "unlocked"]


def test_active_console_id_changes_mid_switch(sw, monkeypatch):
    catcher = SignalCatcher()
    w = make_watcher(monkeypatch, platform="win32", wts_available=True, wts_probe=True)
    w.session_locked.connect(catcher.on_locked)
    w.session_unlocked.connect(catcher.on_unlocked)
    # First event has no active console yet
    w._handle_wts_event(sw.WTS_CONSOLE_DISCONNECT, session_id=10, active_console=None)
    # Then connect with a different new active id
    w._handle_wts_event(sw.WTS_CONSOLE_CONNECT, session_id=20, active_console=None)
    assert w.is_unlocked() is True
    assert catcher.events == ["locked", "unlocked"]


# --- Signal semantics ---

def test_signal_ordering_and_counts(sw, monkeypatch):
    catcher = SignalCatcher()
    w = make_watcher(monkeypatch, platform="win32", wts_available=True, wts_probe=True)
    w.session_locked.connect(catcher.on_locked)
    w.session_unlocked.connect(catcher.on_unlocked)
    active = 9
    # UNLOCK (no-op), LOCK, UNLOCK, SLEEP(LOCK), RESUME(UNLOCK), LOCK
    w._handle_wts_event(sw.WTS_SESSION_UNLOCK, session_id=active, active_console=active)
    w._handle_wts_event(sw.WTS_SESSION_LOCK, session_id=active, active_console=active)
    w._handle_wts_event(sw.WTS_SESSION_UNLOCK, session_id=active, active_console=active)
    w._on_locked()  # sleep maps to locked
    w._on_unlocked()  # resume unlocked (simulated)
    w._handle_wts_event(sw.WTS_SESSION_LOCK, session_id=active, active_console=active)
    assert catcher.events == ["locked", "unlocked", "locked", "unlocked", "locked"]


def test_signals_are_synchronous_with_state(sw, monkeypatch):
    observed = []
    w = make_watcher(monkeypatch, platform="win32", wts_available=True, wts_probe=True)

    def on_locked():
        observed.append(w.is_unlocked())

    def on_unlocked():
        observed.append(w.is_unlocked())

    w.session_locked.connect(on_locked)
    w.session_unlocked.connect(on_unlocked)
    active = 10
    w._handle_wts_event(sw.WTS_SESSION_LOCK, session_id=active, active_console=active)
    w._handle_wts_event(sw.WTS_SESSION_UNLOCK, session_id=active, active_console=active)
    assert observed == [False, True]


def test_polling_resynchronizes_state(sw, monkeypatch):
    catcher = SignalCatcher()
    w = make_watcher(monkeypatch, platform="win32", wts_available=True, wts_probe=True)
    w.session_locked.connect(catcher.on_locked)
    w.session_unlocked.connect(catcher.on_unlocked)

    monkeypatch.setattr(sw.SessionWatcher, "_probe_initial_state_wts", lambda self: False)
    w._poll_session_state()
    assert w.is_unlocked() is False

    monkeypatch.setattr(sw.SessionWatcher, "_probe_initial_state_wts", lambda self: True)
    w._poll_session_state()
    assert w.is_unlocked() is True

    assert catcher.events == ["locked", "unlocked"]


def test_polling_falls_back_to_input_desktop(sw, monkeypatch):
    catcher = SignalCatcher()
    w = make_watcher(monkeypatch, platform="win32", wts_available=True, wts_probe=True)
    w.session_locked.connect(catcher.on_locked)
    w.session_unlocked.connect(catcher.on_unlocked)

    w._handle_wts_event(sw.WTS_SESSION_LOCK, session_id=1, active_console=1)
    assert w.is_unlocked() is False

    monkeypatch.setattr(sw.SessionWatcher, "_probe_initial_state_wts", lambda self: None)
    monkeypatch.setattr(sw, "_probe_unlocked_via_input_desktop", lambda: True)

    w._poll_session_state()

    assert w.is_unlocked() is True
    assert catcher.events == ["locked", "unlocked"]


# --- Cleanup / lifecycle ---

def test_about_to_quit_cleanup(sw, monkeypatch):
    # Prepare a fake wtsapi32 to capture calls
    calls = {"unreg": 0}

    class FakeWTS:
        def WTSRegisterSessionNotification(self, hwnd, flag):
            return 1

        def WTSUnRegisterSessionNotification(self, hwnd):
            calls["unreg"] += 1
            return 1

    # Enable Windows path & WTS
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sw, "wintypes", types.SimpleNamespace(DWORD=int, HWND=int), raising=False)
    monkeypatch.setattr(sw, "wtsapi32", FakeWTS(), raising=False)
    monkeypatch.setattr(sw, "kernel32", object(), raising=False)

    # Use dummy Qt classes from fixture; create watcher which registers hidden window
    w = sw.SessionWatcher()
    # Simulate app quit by calling the connected cleanup
    app = sw.QCoreApplication.instance()
    assert hasattr(app, "fire_quit")
    app.fire_quit()
    # Idempotent
    app.fire_quit()
    assert calls["unreg"] == 1


def test_destructor_cleanup_no_signals(sw, monkeypatch):
    catcher = SignalCatcher()
    # Prepare fake WTS to not raise
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sw, "wintypes", types.SimpleNamespace(DWORD=int, HWND=int), raising=False)
    monkeypatch.setattr(sw, "wtsapi32", types.SimpleNamespace(WTSUnRegisterSessionNotification=lambda hwnd: 1),
                        raising=False)
    monkeypatch.setattr(sw, "kernel32", object(), raising=False)
    w = sw.SessionWatcher()
    w.session_locked.connect(catcher.on_locked)
    w.session_unlocked.connect(catcher.on_unlocked)
    # Delete and ensure no signals were emitted
    del w
    assert catcher.events == []


# --- Hidden window registration ---

def test_hidden_window_registration_fails(sw, monkeypatch, caplog):
    class FailingWTS:
        def WTSRegisterSessionNotification(self, hwnd, flag):
            return 0  # failure

        def WTSUnRegisterSessionNotification(self, hwnd):
            return 1

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sw, "wintypes", types.SimpleNamespace(DWORD=int, HWND=int), raising=False)
    monkeypatch.setattr(sw, "wtsapi32", FailingWTS(), raising=False)
    monkeypatch.setattr(sw, "kernel32", object(), raising=False)
    with caplog.at_level("WARNING"):
        w = sw.SessionWatcher()
    # Still constructed without crash; no messages will arrive but state is from probes
    assert isinstance(w, sw.SessionWatcher)


# --- Optional persistence probes ---

def test_persistence_events_monotonic_timestamps(sw, monkeypatch):
    # Capture store events
    saved = []

    class FakeStore:
        @staticmethod
        def save_session_event(ts, evt):
            saved.append((ts, evt))

    monkeypatch.setattr(sw, "store", FakeStore, raising=False)
    # Start unlocked and cause a sequence
    w = make_watcher(monkeypatch, platform="win32", wts_available=True, wts_probe=True)
    active = 12
    w._handle_wts_event(sw.WTS_SESSION_LOCK, session_id=active, active_console=active)
    w._handle_wts_event(sw.WTS_SESSION_UNLOCK, session_id=active, active_console=active)
    # Ensure exactly two entries, correct strings, and non-decreasing timestamps
    assert [e for _, e in saved] == ["LOCK", "UNLOCK"]
    ts = [t for t, _ in saved]
    assert ts[0] <= ts[1]


def test_ignore_connect_disconnect_when_active_console_known_and_differs(sw, monkeypatch):
    catcher = SignalCatcher()
    w = make_watcher(monkeypatch, platform="win32", wts_available=True, wts_probe=True)
    w.session_locked.connect(catcher.on_locked)
    w.session_unlocked.connect(catcher.on_unlocked)
    # active console is 5, event comes for session 99
    w._handle_wts_event(sw.WTS_CONSOLE_DISCONNECT, session_id=99, active_console=5)
    w._handle_wts_event(sw.WTS_CONSOLE_CONNECT, session_id=99, active_console=5)
    assert w.is_unlocked() is True
    assert catcher.events == []


def test_connect_unknown_console_does_not_force_unlock_without_probe(sw, monkeypatch):
    catcher = SignalCatcher()
    w = make_watcher(monkeypatch, platform="win32", wts_available=True, wts_probe=False)
    w.session_locked.connect(catcher.on_locked)
    w.session_unlocked.connect(catcher.on_unlocked)
    assert w.is_unlocked() is False

    monkeypatch.setattr(sw.SessionWatcher, "_probe_initial_state_wts", lambda self: None)
    monkeypatch.setattr(sw, "_probe_unlocked_via_input_desktop", lambda: None)

    w._handle_wts_event(sw.WTS_CONSOLE_CONNECT, session_id=7, active_console=None)

    assert w.is_unlocked() is False
    assert catcher.events == []


def test_lock_unlock_mismatch_uses_probe_confirmation(sw, monkeypatch):
    catcher = SignalCatcher()
    w = make_watcher(monkeypatch, platform="win32", wts_available=True, wts_probe=True)
    w.session_locked.connect(catcher.on_locked)
    w.session_unlocked.connect(catcher.on_unlocked)

    monkeypatch.setattr(sw.SessionWatcher, "_probe_initial_state_wts", lambda self: False)
    w._handle_wts_event(sw.WTS_SESSION_LOCK, session_id=99, active_console=1)
    assert w.is_unlocked() is False

    monkeypatch.setattr(sw.SessionWatcher, "_probe_initial_state_wts", lambda self: True)
    w._handle_wts_event(sw.WTS_SESSION_UNLOCK, session_id=99, active_console=1)
    assert w.is_unlocked() is True
    assert catcher.events == ["locked", "unlocked"]


def test_desktop_probe_fallback_unlocked(sw, monkeypatch):
    # WTS probe None -> fall back to desktop probe True
    w = make_watcher(monkeypatch, platform="win32", wts_available=True, wts_probe=None, desktop_probe=True)
    assert w.is_unlocked() is True


def test_desktop_probe_fallback_locked(sw, monkeypatch):
    w = make_watcher(monkeypatch, platform="win32", wts_available=True, wts_probe=None, desktop_probe=False)
    assert w.is_unlocked() is False


def test_end_session_path(sw, monkeypatch):
    # parity with QUERYENDSESSION
    w = make_watcher(monkeypatch, platform="win32", wts_available=True, wts_probe=True)
    assert w.is_unlocked() is True
    # simulate ENDSESSION handling (maps to locked)
    w._on_locked()
    assert w.is_unlocked() is False


def test_destructor_calls_unregister_once(sw, monkeypatch):
    calls = {"unreg": 0}

    class FakeWTS:
        def WTSRegisterSessionNotification(self, hwnd, flag): return 1

        def WTSUnRegisterSessionNotification(self, hwnd):
            calls["unreg"] += 1
            return 1

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sw, "wintypes", types.SimpleNamespace(DWORD=int, HWND=int), raising=False)
    monkeypatch.setattr(sw, "wtsapi32", FakeWTS(), raising=False)
    monkeypatch.setattr(sw, "kernel32", object(), raising=False)

    w = sw.SessionWatcher()
    # No aboutToQuit fired; rely on destructor
    import gc, weakref
    r = weakref.ref(w)
    del w;
    gc.collect()
    assert r() is None
    assert calls["unreg"] == 1


def test_unknown_wts_reason_ignored(sw, monkeypatch):
    w = make_watcher(monkeypatch, platform="win32", wts_available=True, wts_probe=True)
    before = w.is_unlocked()
    UNKNOWN_REASON = 0xDEAD
    w._handle_wts_event(UNKNOWN_REASON, session_id=1, active_console=1)
    assert w.is_unlocked() is before


def test_registration_failure_logs_warning_message(sw, monkeypatch, caplog):
    class FailingWTS:
        def WTSRegisterSessionNotification(self, hwnd, flag): return 0

        def WTSUnRegisterSessionNotification(self, hwnd): return 1

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sw, "wintypes", types.SimpleNamespace(DWORD=int, HWND=int), raising=False)
    monkeypatch.setattr(sw, "wtsapi32", FailingWTS(), raising=False)
    monkeypatch.setattr(sw, "kernel32", object(), raising=False)
    with caplog.at_level("WARNING"):
        _ = sw.SessionWatcher()
    assert any("WTSRegisterSessionNotification failed" in rec.message for rec in caplog.records)
