"""OS notifications abstraction.

For Windows 10/11 toast notifications, the `winrt` package provides access
via Windows.UI.Notifications. This module exposes a simple function with a
no-op fallback in case toasts are unavailable.
"""
from __future__ import annotations

import sys

try:
    # Runtime import so running on non-Windows or without winrt doesn't break import
    from winrt.windows.ui.notifications import ToastNotificationManager  # type: ignore
    from winrt.windows.data.xml.dom import XmlDocument  # type: ignore
except Exception:  # pragma: no cover - best effort fallback
    ToastNotificationManager = None  # type: ignore
    XmlDocument = None  # type: ignore


def notify(title: str, message: str) -> None:
    """Show a notification with best effort safety.

    Behavior:
      - If configured and available on Windows, use WinRT toast (optionally with sound).
      - Fallback to QSystemTrayIcon.showMessage if a tray is available (set by main as notifier.tray).
      - Final fallback to stderr print.
    Never raises.
    """
    try:
        # Load config lazily to avoid hard dependency at import time
        try:
            from ..config import load_config  # type: ignore
        except Exception:  # pragma: no cover
            from deskcoach.config import load_config  # type: ignore
        app_cfg = load_config().app
        use_toast = bool(getattr(app_cfg, "use_windows_toast", True))
        play_sound = bool(getattr(app_cfg, "play_sound", True))

        # Attempt Windows toast first if allowed
        if sys.platform.startswith("win") and use_toast and ToastNotificationManager is not None and XmlDocument is not None:
            try:
                xml = XmlDocument()
                # Add optional audio
                audio_tag = (
                    "<audio src=\"ms-winsoundevent:Notification.Default\"/>" if play_sound else "<audio silent=\"true\"/>"
                )
                xml.load_xml(
                    f"""
                    <toast>
                        <visual>
                            <binding template=\"ToastGeneric\">\n\
                                <text>{title}</text>\n\
                                <text>{message}</text>\n\
                            </binding>
                        </visual>
                        {audio_tag}
                    </toast>
                    """
                )
                notifier_obj = ToastNotificationManager.create_toast_notifier("DeskCoach")
                from winrt.windows.ui.notifications import ToastNotification  # type: ignore
                notifier_obj.show(ToastNotification(xml))
                return
            except Exception:
                # Fall through to tray fallback
                pass

        # Fallback to existing tray icon, if main assigned notifier.tray = tray
        try:
            from PyQt6.QtWidgets import QSystemTrayIcon  # type: ignore
            tray = globals().get("tray")
            if isinstance(tray, QSystemTrayIcon):
                tray.showMessage(title, message)
                return
        except Exception:
            pass
    except Exception:
        # Ignore any errors fetching config, etc.
        pass

    # Final fallback: print to stderr
    try:
        print(f"[Notification] {title}: {message}", file=sys.stderr)
    except Exception:
        # Nothing else we can do
        pass
