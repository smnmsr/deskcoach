from __future__ import annotations

import sys
import ctypes
import logging
from datetime import datetime
from typing import Optional

from PyQt6.QtCore import QObject, QAbstractNativeEventFilter, QCoreApplication, Qt, pyqtSignal as Signal
from PyQt6.QtWidgets import QWidget

# Optional import to persist session events
try:
    from ..models import store  # when running as package
except Exception:  # pragma: no cover
    try:
        from deskcoach.models import store  # type: ignore
    except Exception:
        store = None  # type: ignore

log = logging.getLogger(__name__)

# Windows message and WTS constants
WM_WTSSESSION_CHANGE = 0x02B1
WTS_SESSION_LOCK = 0x7
WTS_SESSION_UNLOCK = 0x8

# Guarded access to ctypes.wintypes; some environments may lack it
try:
    from ctypes import wintypes  # type: ignore
except Exception:
    wintypes = None  # type: ignore

if sys.platform.startswith("win") and wintypes is not None:
    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    wtsapi32 = ctypes.windll.wtsapi32  # type: ignore[attr-defined]
else:
    user32 = None
    wtsapi32 = None


class _NativeFilter(QAbstractNativeEventFilter):
    """Global native event filter to watch for WM_WTSSESSION_CHANGE.

    We still require that at least one window is registered for session
    notifications. SessionWatcher creates a hidden QWidget and registers it.
    """

    def __init__(self, owner: "SessionWatcher") -> None:
        super().__init__()
        self._owner = owner

    def nativeEventFilter(self, eventType: bytes, message: int) -> tuple[bool, int]:  # type: ignore[override]
        if not sys.platform.startswith("win") or wintypes is None:
            return False, 0
        try:
            if eventType != b"windows_generic_MSG":
                return False, 0
            # message is a pointer to MSG
            MSG = wintypes.MSG  # type: ignore[attr-defined]
            msg = MSG.from_address(int(message))
            if msg.message == WM_WTSSESSION_CHANGE:
                wparam = int(msg.wParam)
                if wparam == WTS_SESSION_LOCK:
                    self._owner._on_locked()
                elif wparam == WTS_SESSION_UNLOCK:
                    self._owner._on_unlocked()
        except Exception as e:  # pragma: no cover - defensive
            log.debug("nativeEventFilter error: %s", e)
        return False, 0


class SessionWatcher(QObject):
    """Qt-based watcher for Windows session lock/unlock events.

    Emits:
      - session_locked
      - session_unlocked

    Use is_unlocked() to query current state.
    """

    session_locked = Signal()
    session_unlocked = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._unlocked: bool = True
        self._lock_changed_at: Optional[datetime] = None
        self._widget: Optional[QWidget] = None
        self._filter = _NativeFilter(self)
        QCoreApplication.instance().installNativeEventFilter(self._filter)  # type: ignore[arg-type]
        self._register_hidden_window()

    def _register_hidden_window(self) -> None:
        if not sys.platform.startswith("win"):
            log.info("SessionWatcher active: non-Windows platform, treating as always unlocked.")
            return
        try:
            w = QWidget()
            w.setWindowTitle("SessionWatcherHidden")
            w.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
            w.resize(0, 0)
            w.setVisible(False)
            if wintypes is None or wtsapi32 is None:
                log.warning("SessionWatcher: ctypes.wintypes unavailable; treating as always unlocked.")
                self._widget = None
                return
            hwnd = int(w.winId())
            # Register this window for session notifications
            if not bool(wtsapi32.WTSRegisterSessionNotification(wintypes.HWND(hwnd), wintypes.DWORD(0))):  # type: ignore[attr-defined]
                log.warning("WTSRegisterSessionNotification failed")
            else:
                log.debug("SessionWatcher registered for WTS notifications (hwnd=%s)", hwnd)
            self._widget = w
        except Exception as e:  # pragma: no cover - best effort
            log.warning("Failed to register session notifications: %s", e)
            self._widget = None

    def is_unlocked(self) -> bool:
        return self._unlocked

    # Internal handlers
    def _on_locked(self) -> None:
        if not self._unlocked:
            return
        self._unlocked = False
        self._lock_changed_at = datetime.now()
        # Persist event
        try:
            if store is not None:
                ts = int(self._lock_changed_at.timestamp())
                store.save_session_event(ts, "LOCK")  # type: ignore[attr-defined]
        except Exception as e:  # pragma: no cover
            log.debug("Failed to save LOCK event: %s", e)
        log.info("Session locked: pausing polling and reminders.")
        self.session_locked.emit()

    def _on_unlocked(self) -> None:
        if self._unlocked:
            return
        self._unlocked = True
        self._lock_changed_at = datetime.now()
        # Persist event
        try:
            if store is not None:
                ts = int(self._lock_changed_at.timestamp())
                store.save_session_event(ts, "UNLOCK")  # type: ignore[attr-defined]
        except Exception as e:  # pragma: no cover
            log.debug("Failed to save UNLOCK event: %s", e)
        log.info("Session unlocked: resuming polling and reminders.")
        self.session_unlocked.emit()

    def __del__(self) -> None:  # pragma: no cover - cleanup best effort
        try:
            if sys.platform.startswith("win") and self._widget is not None and wintypes is not None and wtsapi32 is not None:
                hwnd = int(self._widget.winId())
                try:
                    wtsapi32.WTSUnRegisterSessionNotification(wintypes.HWND(hwnd))  # type: ignore[attr-defined]
                except Exception:
                    pass
        except Exception:
            pass
