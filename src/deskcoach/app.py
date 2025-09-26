"""Application wiring (optional).

This module can be used to set up QApplication and any dependency injection
or service wiring separate from the CLI/entry point in main.py.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QApplication

from .utils.qt_helpers import apply_modern_style


def build_app(existing: Optional[QApplication] = None, theme: str = "auto") -> QApplication:
    """Return a QApplication instance, creating one if needed, and apply modern styling.

    Also ensures the app keeps running in the tray when the last window is closed.
    """
    app = existing or QApplication.instance()  # type: ignore[assignment]
    if app is None:
        app = QApplication([])
    # Do not quit when the last window is closed (tray app behavior)
    try:
        app.setQuitOnLastWindowClosed(False)
    except Exception:
        pass
    # Apply a modern look (Fusion + palette + stylesheet)
    apply_modern_style(app, theme=theme)
    return app
