"""OS notifications abstraction.

Refactored to rely solely on the application's system tray integration
(QSystemTrayIcon.showMessage). On Windows, Qt routes this to native
Windows notifications when available. There is no separate WinRT path
anymore. Falls back to stderr if no tray is present.
"""
from __future__ import annotations

import sys


def notify(title: str, message: str) -> None:
    """Show a notification using the tray if available, else stderr. Never raises."""
    # Try the existing tray icon, if main assigned notifier.tray = tray
    try:
        from PyQt6.QtWidgets import QSystemTrayIcon  # type: ignore
        tray = globals().get("tray")
        if isinstance(tray, QSystemTrayIcon):
            tray.showMessage(title, message)
            return
    except Exception:
        # Ignore PyQt import or usage issues and fall back
        pass

    # Final fallback: print to stderr
    print(f"[Notification] {title}: {message}", file=sys.stderr)
