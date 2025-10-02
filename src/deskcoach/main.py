import sys
import time
import logging
from typing import Optional

# Allow running as a script (python path/to/deskcoach/main.py) by adding src to sys.path
try:
    # When run directly, __package__ is empty; insert the project src folder for absolute imports
    if not __package__:
        from pathlib import Path as _Path
        _src = _Path(__file__).resolve().parents[1]
        if str(_src) not in sys.path:
            sys.path.insert(0, str(_src))
except Exception:
    pass

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QStyle, QMainWindow, QWidget, QVBoxLayout, QPushButton, QDialog, QFormLayout, QLineEdit, QDoubleSpinBox, QSpinBox, QCheckBox, QMessageBox, QHBoxLayout
from PyQt6.QtGui import QIcon, QAction

try:
    from .app import build_app
except ImportError:
    from deskcoach.app import build_app

try:
    from .services import api_client, notifier  # when running as a package (python -m deskcoach.main)
    from .models import store
    from .config import load_config
    from .services.session_watcher import SessionWatcher
    from .services.reminder import ReminderEngine
except ImportError:
    from deskcoach.services import api_client, notifier  # absolute fallback
    from deskcoach.models import store
    from deskcoach.config import load_config
    from deskcoach.services.session_watcher import SessionWatcher
    from deskcoach.services.reminder import ReminderEngine

# UI views are now defined in deskcoach.views
try:
    from .views import MainWindow, SettingsDialog
except ImportError:
    from deskcoach.views import MainWindow, SettingsDialog  # type: ignore

def _load_app_icon() -> QIcon:
    """Load app icon from packaged resources, with graceful fallbacks."""
    try:
        from importlib.resources import files, as_file
        # Prefer a 32px PNG for tray clarity
        icon_res = files("deskcoach.resources.icons") / "icon_32px.png"
        if not icon_res.is_file():
            icon_res = files("deskcoach.resources.icons") / "icon.ico"
        with as_file(icon_res) as p:
            return QIcon(str(p))
    except Exception:
        pass
    # Last resort: a standard system icon
    try:
        from PyQt6.QtWidgets import QApplication, QStyle
        app = QApplication.instance()
        if app is not None:
            return app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
    except Exception:
        pass
    return QIcon()


def create_tray_icon(app: QApplication) -> QSystemTrayIcon:
    icon: QIcon = _load_app_icon()

    tray = QSystemTrayIcon(icon, app)

    # Context menu with Close action; additional actions will be added in main()
    menu = QMenu()
    close_action = QAction("Close", menu)

    def _confirm_quit():
        try:
            from PyQt6.QtWidgets import QMessageBox
            res = QMessageBox.question(
                None,
                "Quit DeskCoach",
                "Are you sure you want to close DeskCoach?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if res == QMessageBox.StandardButton.Yes:
                app.quit()
        except Exception:
            # Fallback: do nothing if confirmation fails
            pass

    close_action.triggered.connect(_confirm_quit)
    menu.addAction(close_action)

    tray.setContextMenu(menu)
    tray.setToolTip("DeskCoach")
    tray.show()

    return tray


def main() -> int:
    # Basic logging to something (will refine after config/db known)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log = logging.getLogger("deskcoach")

    ns = load_config()
    cfg = ns.app

    # Ensure database exists and determine data folder for logs
    db_path = store.init_db()
    data_dir = db_path.parent

    # Configure file logging in the same folder as the database
    try:
        logfile = data_dir / "deskcoach.log"
        root_logger = logging.getLogger()
        # Set overall level from config
        level_name = str(getattr(cfg, "log_level", "INFO")).upper()
        level = getattr(logging, level_name, logging.INFO)
        root_logger.setLevel(level)
        # Avoid adding duplicate file handlers
        has_file = False
        for h in root_logger.handlers:
            try:
                if isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", None):
                    if str(h.baseFilename) == str(logfile):
                        has_file = True
                        break
            except Exception:
                continue
        if not has_file:
            fh = logging.FileHandler(str(logfile), encoding="utf-8")
            fh.setLevel(level)
            fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
            fh.setFormatter(fmt)
            root_logger.addHandler(fh)
        log.info("Logging to %s (level %s)", logfile, level_name)
    except Exception:
        pass

    log.info("Starting DeskCoach; polling %s every %s minutes", cfg.base_url, cfg.poll_minutes)
    log.info("DB at %s", db_path)

    # Build application with modern styling; pass theme from config if present
    app = build_app(theme=str(getattr(cfg, "theme", "auto")))
    # Set application icon from resources
    try:
        app_icon = _load_app_icon()
        app.setWindowIcon(app_icon)
    except Exception:
        pass
    # Keep references so they're not garbage-collected
    tray = create_tray_icon(app)
    main_window = MainWindow(ns)
    try:
        main_window.setWindowIcon(app_icon)
    except Exception:
        pass
    # Expose tray to notifier fallback
    try:
        notifier.tray = tray  # type: ignore[attr-defined]
    except Exception:
        pass

    # Session watcher and reminder engine
    watcher = SessionWatcher()
    reminder_engine = ReminderEngine(cfg, watcher)


    # Extend tray menu with actions
    menu = tray.contextMenu()

    # App state to allow live updates from settings
    app_state = {
        "ns": ns,
        "cfg": cfg,
        "snooze_minutes": int(getattr(cfg, "snooze_minutes", 30)),
    }

    # Open main window action
    open_action = QAction("Open DeskCoach…", menu)
    def open_main_window():
        main_window.show()
        main_window.raise_()
        main_window.activateWindow()
    open_action.triggered.connect(open_main_window)

    # Open on tray single click or double-click
    try:
        def _on_tray_activated(reason):
            try:
                # Respond to left single click (Trigger) and double-click
                if reason in (
                    QSystemTrayIcon.ActivationReason.Trigger,
                    QSystemTrayIcon.ActivationReason.DoubleClick,
                ):
                    open_main_window()
            except Exception:
                pass
        tray.activated.connect(_on_tray_activated)
    except Exception:
        # If tray activation connection fails, ignore
        pass

    # Snooze action
    snooze_action = QAction(f"Snooze {app_state['snooze_minutes']} min", menu)
    def do_snooze():
        reminder_engine.snooze(app_state["snooze_minutes"]) 
        log.info("User snoozed reminders for %s minutes", app_state["snooze_minutes"])
    snooze_action.triggered.connect(do_snooze)

    # Insert actions before Exit
    actions = menu.actions()
    if actions:
        menu.insertAction(actions[0], open_action)
        menu.insertAction(actions[0], snooze_action)
    else:
        menu.addAction(open_action)
        menu.addAction(snooze_action)

    # Log on lock/unlock
    watcher.session_locked.connect(lambda: log.info("System locked: polling suspended"))
    watcher.session_unlocked.connect(lambda: log.info("System unlocked: polling resumed"))

    # Define the polling function
    def poll_once() -> None:
        # Skip polling when session is locked
        try:
            if not watcher.is_unlocked():
                return
        except Exception:
            # if watcher fails, proceed
            pass
        try:
            current_cfg = app_state["cfg"]
            height_mm = api_client.get_height_mm(current_cfg.base_url)
            ts = int(time.time())
            store.save_measurement(ts, height_mm)
            log.info("Measurement saved: ts=%s height_mm=%s", ts, height_mm)
            # Feed reminder engine
            try:
                reminder_engine.on_new_measurement(ts, height_mm)
            except Exception:
                pass
        except Exception as e:
            log.warning("Polling failed: %s", e)

    # Set up the timer
    timer = QTimer()
    interval_ms = int(cfg.poll_minutes * 60_000)
    if interval_ms <= 0:
        interval_ms = 1  # minimum to avoid invalid timer
    timer.setInterval(interval_ms)
    timer.timeout.connect(poll_once)
    timer.start()

    # Optional: handle app aboutToQuit cleanup
    def _cleanup():
        tray.hide()
        try:
            main_window.hide()
        except Exception:
            pass

    app.aboutToQuit.connect(_cleanup)

    # Kick an immediate first poll without waiting full interval
    QTimer.singleShot(0, poll_once)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
