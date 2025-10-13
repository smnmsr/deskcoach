from __future__ import annotations

import sys
import ctypes
import logging
import weakref
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
# Additional WTS reason codes
WTS_CONSOLE_CONNECT    = 0x1
WTS_CONSOLE_DISCONNECT = 0x2
WTS_REMOTE_CONNECT     = 0x3
WTS_REMOTE_DISCONNECT  = 0x4
WTS_SESSION_LOGON      = 0x5
WTS_SESSION_LOGOFF     = 0x6

# Shutdown/power broadcast messages (optional hygiene)
WM_QUERYENDSESSION = 0x0011
WM_ENDSESSION      = 0x0016
WM_POWERBROADCAST  = 0x0218
PBT_APMSUSPEND     = 0x0004
PBT_APMRESUMEAUTOMATIC = 0x0012
PBT_APMRESUMESUSPEND  = 0x0007

# WTSRegisterSessionNotification flags
NOTIFY_FOR_THIS_SESSION = 0
NOTIFY_FOR_ALL_SESSIONS = 1

# WTSQuerySessionInformation indexes
WTS_CURRENT_SERVER_HANDLE = None
WTS_CURRENT_SESSION = -1
WTSSessionInfoEx = 24

# Guarded access to ctypes.wintypes; some environments may lack it
try:
    from ctypes import wintypes  # type: ignore
except Exception:
    wintypes = None  # type: ignore

if sys.platform.startswith("win") and wintypes is not None:
    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    wtsapi32 = ctypes.windll.wtsapi32  # type: ignore[attr-defined]
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    # Set restype once for WTSGetActiveConsoleSessionId to avoid repeated assignment
    try:
        kernel32.WTSGetActiveConsoleSessionId.restype = wintypes.DWORD  # type: ignore[attr-defined]
    except Exception:
        pass
    # Improve signatures for WTS (un)register
    try:
        wtsapi32.WTSRegisterSessionNotification.argtypes = [wintypes.HWND, wintypes.DWORD]  # type: ignore[attr-defined]
        wtsapi32.WTSRegisterSessionNotification.restype = wintypes.BOOL  # type: ignore[attr-defined]
        wtsapi32.WTSUnRegisterSessionNotification.argtypes = [wintypes.HWND]  # type: ignore[attr-defined]
        wtsapi32.WTSUnRegisterSessionNotification.restype = wintypes.BOOL  # type: ignore[attr-defined]
    except Exception:
        pass
else:
    user32 = None
    wtsapi32 = None
    kernel32 = None


def _probe_unlocked_via_input_desktop() -> Optional[bool]:
    """Probe initial unlocked state via the input desktop name.

    Returns True if the input desktop is "Default" (typical for unlocked),
    False if it is known locked desktops (e.g., Winlogon/Screen-saver),
    or None if unavailable.
    """
    if not sys.platform.startswith("win") or user32 is None or wintypes is None:
        return None
    DESKTOP_READOBJECTS = 0x0001
    DESKTOP_SWITCHDESKTOP = 0x0100
    try:
        OpenInputDesktop = user32.OpenInputDesktop
        OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        OpenInputDesktop.restype = wintypes.HDESK

        GetUserObjectInformationW = user32.GetUserObjectInformationW
        GetUserObjectInformationW.argtypes = [wintypes.HANDLE, wintypes.INT,
                                              ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
        GetUserObjectInformationW.restype = wintypes.BOOL

        CloseDesktop = user32.CloseDesktop
        CloseDesktop.argtypes = [wintypes.HDESK]
        CloseDesktop.restype = wintypes.BOOL

        hdesk = OpenInputDesktop(0, False, DESKTOP_READOBJECTS | DESKTOP_SWITCHDESKTOP)
        if not hdesk:
            return None
        try:
            UOI_NAME = 2
            sz = wintypes.DWORD(0)
            # First call to get required buffer size
            GetUserObjectInformationW(hdesk, UOI_NAME, None, 0, ctypes.byref(sz))
            if sz.value == 0:
                return None
            length = max(1, sz.value // ctypes.sizeof(wintypes.WCHAR))
            buf = ctypes.create_unicode_buffer(length)
            if not GetUserObjectInformationW(hdesk, UOI_NAME, buf, sz, ctypes.byref(sz)):
                log.debug("GetUserObjectInformationW failed on second call; unable to read input desktop name")
                return None
            name = buf.value
            return name.lower() == "default"
        finally:
            CloseDesktop(hdesk)
    except Exception:
        return None


def _get_active_console_session_id() -> Optional[int]:
    """Return the current active console SessionId, or None if unavailable."""
    if not sys.platform.startswith("win") or wintypes is None or kernel32 is None:
        return None
    try:
        sid = int(kernel32.WTSGetActiveConsoleSessionId())  # type: ignore[attr-defined]
        # 0xFFFFFFFF (DWORD -1) means no session
        if sid == 0xFFFFFFFF:
            return None
        return sid
    except Exception:
        return None


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
            if eventType not in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
                return False, 0
            # message is a pointer to MSG
            MSG = wintypes.MSG  # type: ignore[attr-defined]
            msg = MSG.from_address(int(message))
            if msg.message == WM_WTSSESSION_CHANGE:
                reason = int(msg.wParam)
                session_id = int(msg.lParam)
                active_console = _get_active_console_session_id()
                log.debug("WTS change: reason=%s session=%s active_console=%s", reason, session_id, active_console)
                # Delegate to owner logic to handle filtering and transitions
                try:
                    self._owner._handle_wts_event(reason, session_id, active_console)
                except Exception as _e:
                    log.debug("_handle_wts_event error: %s", _e)
            elif msg.message == WM_QUERYENDSESSION:
                # System is shutting down/logging off; mark as not usable
                self._owner._on_locked()
            elif msg.message == WM_ENDSESSION:
                # Some apps only receive ENDSESSION; ensure we mark locked
                self._owner._on_locked()
            elif msg.message == WM_POWERBROADCAST and int(msg.wParam) == PBT_APMSUSPEND:
                # Going to sleep/hibernate; mark as not usable
                self._owner._on_locked()
            elif msg.message == WM_POWERBROADCAST and int(msg.wParam) in (PBT_APMRESUMEAUTOMATIC, PBT_APMRESUMESUSPEND):
                # On resume, re-probe; there may be no explicit UNLOCK event
                state = self._owner._probe_initial_state_wts()
                if state is None:
                    state = _probe_unlocked_via_input_desktop()
                if state is True:
                    self._owner._on_unlocked()
                elif state is False:
                    self._owner._on_locked()
        except Exception as e:  # pragma: no cover - defensive
            log.debug("nativeEventFilter error: %s", e)
        return False, 0


class SessionWatcher(QObject):
    """Qt-based watcher for Windows session lock/unlock events, scoped to the local console.

    Emits:
      - session_locked
      - session_unlocked

    Use is_unlocked() to query current state.
    """

    session_locked = Signal()
    session_unlocked = Signal()

    def __init__(self) -> None:
        super().__init__()
        # Start pessimistically as locked; probes and first WTS event will correct if needed.
        self._unlocked: bool = False
        self._lock_changed_at: Optional[datetime] = None
        self._widget: Optional[QWidget] = None
        self._unregistered: bool = False
        self._wts_registered: bool = False
        self._filter = _NativeFilter(self)

        # If not on Windows or WTS/ctypes not available, treat as always unlocked and return early.
        if not sys.platform.startswith("win"):
            self._unlocked = True
            log.info("SessionWatcher active: non-Windows platform, treating as always unlocked.")
            return
        if wintypes is None or wtsapi32 is None:
            self._unlocked = True
            self._widget = None
            log.info("SessionWatcher: WTS/ctypes unavailable; treating as always unlocked.")
            return

        app = QCoreApplication.instance()
        if app is not None:
            app.installNativeEventFilter(self._filter)  # type: ignore[arg-type]
        else:
            log.warning("SessionWatcher: no QCoreApplication instance; native filter not installed yet.")

        # Create and register the hidden window only when a GUI app exists; otherwise, defer
        if app is not None:
            self._register_hidden_window()
        else:
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, self._register_hidden_window)

        # Probe initial state at startup via WTS; fall back to input desktop if needed
        try:
            wts_unlocked = self._probe_initial_state_wts()
        except Exception:
            wts_unlocked = None
        if wts_unlocked is not None:
            self._unlocked = wts_unlocked
            log.info("Initial state via WTS: unlocked=%s", wts_unlocked)
        else:
            unlocked = _probe_unlocked_via_input_desktop()
            if unlocked is not None:
                self._unlocked = unlocked
                log.info("Initial state via input desktop: unlocked=%s", unlocked)
            else:
                log.info("Initial state probe unavailable; defaulting to %s", self._unlocked)

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
            # Register this window for session notifications (ALL sessions; we filter to console)
            if not bool(
                wtsapi32.WTSRegisterSessionNotification(  # type: ignore[attr-defined]
                    wintypes.HWND(hwnd), wintypes.DWORD(NOTIFY_FOR_ALL_SESSIONS)
                )
            ):
                log.warning("WTSRegisterSessionNotification failed")
            else:
                log.debug("SessionWatcher registered for WTS notifications (hwnd=%s, all sessions)", hwnd)
                self._wts_registered = True
            self._widget = w
            try:
                app2 = QCoreApplication.instance()
                if app2 is not None:
                    owner_ref = weakref.ref(self)
                    def _cleanup():
                        owner = owner_ref()
                        if owner is None:
                            return
                        if owner._unregistered:
                            return
                        owner._unregistered = True
                        try:
                            if owner._wts_registered and owner._widget is not None and wtsapi32 is not None and wintypes is not None:
                                owner._wts_registered = False  # flip first to prevent double-unregister
                                hwnd2 = int(owner._widget.winId())
                                try:
                                    wtsapi32.WTSUnRegisterSessionNotification(wintypes.HWND(hwnd2))  # type: ignore[attr-defined]
                                except Exception:
                                    pass
                        except Exception:
                            pass
                        try:
                            app3 = QCoreApplication.instance()
                            if app3 is not None:
                                try:
                                    app3.removeNativeEventFilter(owner._filter)  # type: ignore[arg-type]
                                except Exception:
                                    pass
                        except Exception:
                            pass
                    app2.aboutToQuit.connect(_cleanup)  # type: ignore[arg-type]
            except Exception:
                pass
        except Exception as e:  # pragma: no cover - best effort
            log.warning("Failed to register session notifications: %s", e)
            self._widget = None


    def _probe_initial_state_wts(self) -> Optional[bool]:
        """Probe initial lock state using WTSSessionInfoEx SessionFlags.

        Returns True for unlocked, False for locked, or None on failure.
        """
        if not sys.platform.startswith("win") or wintypes is None or wtsapi32 is None:
            return None
        try:
            WTSQuerySessionInformationW = wtsapi32.WTSQuerySessionInformationW  # type: ignore[attr-defined]
            WTSQuerySessionInformationW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                                                    ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.DWORD)]
            WTSQuerySessionInformationW.restype = wintypes.BOOL

            buf = ctypes.c_void_p()
            bytes_ret = wintypes.DWORD(0)
            ok = WTSQuerySessionInformationW(WTS_CURRENT_SERVER_HANDLE, wintypes.DWORD(WTS_CURRENT_SESSION),
                                             wintypes.DWORD(WTSSessionInfoEx), ctypes.byref(buf), ctypes.byref(bytes_ret))
            if not ok or not buf:
                return None
            try:
                # Interpret buffer dynamically to avoid struct layout fragility across OS builds.
                # bytes_ret is the total size in bytes. First DWORD is Level; for Level==1
                # SessionFlags is documented to be the last DWORD of the Level1 block.
                addr = int(ctypes.cast(buf, ctypes.c_void_p).value)
                total = int(bytes_ret.value)
                if total < 16:
                    return None
                raw = (ctypes.c_ubyte * total).from_address(addr)
                level = int.from_bytes(bytes(raw[0:4]), "little")
                if level != 1:
                    return None
                session_flags = int.from_bytes(bytes(raw[total-4:total]), "little")
                if session_flags == 0:
                    return False
                if session_flags == 1:
                    return True
                log.debug("WTSSessionInfoEx SessionFlags unexpected value: %s (total=%s)", session_flags, total)
                return None
            finally:
                try:
                    wtsapi32.WTSFreeMemory(buf)  # type: ignore[attr-defined]
                except Exception:
                    pass
        except Exception:
            return None

    def is_unlocked(self) -> bool:
        return self._unlocked

    # Exposed for testing: handle a WTS event with given reason/session and known active console
    def _handle_wts_event(self, reason: int, session_id: int, active_console: Optional[int]) -> None:
        # Accept CONNECT/DISCONNECT only when active_console is unknown (switch in progress)
        if active_console is None:
            if reason == WTS_CONSOLE_DISCONNECT:
                self._on_locked()
                return
            if reason == WTS_CONSOLE_CONNECT:
                self._on_unlocked()
                return
            return
        # With a known active_console, ignore events not for that session (including CONNECT/DISCONNECT)
        if session_id != active_console:
            log.info(
                "Ignoring WTS change for non-console session: reason=%s, session=%s, active_console=%s",
                reason,
                session_id,
                active_console,
            )
            return
        # Process events for the active console session
        if reason == WTS_SESSION_LOCK:
            self._on_locked()
        elif reason == WTS_SESSION_UNLOCK:
            self._on_unlocked()
        elif reason == WTS_CONSOLE_DISCONNECT:
            self._on_locked()
        elif reason == WTS_CONSOLE_CONNECT:
            self._on_unlocked()

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
        log.info("Session locked (local console): pausing polling and reminders.")
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
        log.info("Session unlocked (local console): resuming polling and reminders.")
        self.session_unlocked.emit()

    def __del__(self) -> None:  # pragma: no cover - cleanup best effort
        try:
            if getattr(self, "_unregistered", False):
                return
            self._unregistered = True
            if sys.platform.startswith("win") and getattr(self, "_widget", None) is not None \
               and wintypes is not None and wtsapi32 is not None and getattr(self, "_wts_registered", False):
                self._wts_registered = False  # flip first
                hwnd = int(self._widget.winId())
                try:
                    wtsapi32.WTSUnRegisterSessionNotification(wintypes.HWND(hwnd))  # type: ignore[attr-defined]
                except Exception:
                    pass
            try:
                app = QCoreApplication.instance()
                if app is not None:
                    try:
                        app.removeNativeEventFilter(self._filter)  # type: ignore[arg-type]
                    except Exception:
                        pass
            except Exception:
                pass
        except Exception:
            pass
