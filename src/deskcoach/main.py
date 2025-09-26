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
from PyQt6.QtGui import QIcon, QAction, QPixmap

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

    # Context menu with Exit action; additional actions will be added in main()
    menu = QMenu()
    exit_action = QAction("Exit", menu)
    exit_action.triggered.connect(app.quit)
    menu.addAction(exit_action)

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

    # State for user-paused polling
    state = {"paused": False}

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

    # Settings action
    settings_action = QAction("Settings…", menu)
    def open_settings():
        dlg = SettingsDialog(main_window, app_state["ns"])
        if dlg.exec() == QDialog.Accepted:
            # Reload config and apply live
            new_ns = load_config()
            app_state["ns"] = new_ns
            app_state["cfg"] = new_ns.app
            main_window._cfg_ns = new_ns
            # Update timer interval
            new_interval_ms = int(max(0.001, float(app_state["cfg"].poll_minutes)) * 60_000)
            if new_interval_ms <= 0:
                new_interval_ms = 1
            timer.setInterval(new_interval_ms)
            # Update snooze default and label
            app_state["snooze_minutes"] = int(getattr(app_state["cfg"], "snooze_minutes", 30))
            snooze_action.setText(f"Snooze {app_state['snooze_minutes']} min")
            # Update ReminderEngine config
            try:
                rcfg = reminder_engine.cfg
                rcfg.stand_threshold_mm = int(getattr(app_state["cfg"], "stand_threshold_mm", rcfg.stand_threshold_mm))
                rcfg.remind_after_minutes = int(getattr(app_state["cfg"], "remind_after_minutes", rcfg.remind_after_minutes))
                rcfg.remind_repeat_minutes = int(getattr(app_state["cfg"], "remind_repeat_minutes", rcfg.remind_repeat_minutes))
                rcfg.standing_check_after_minutes = int(getattr(app_state["cfg"], "standing_check_after_minutes", rcfg.standing_check_after_minutes))
                rcfg.standing_check_repeat_minutes = int(getattr(app_state["cfg"], "standing_check_repeat_minutes", rcfg.standing_check_repeat_minutes))
                rcfg.snooze_minutes = int(getattr(app_state["cfg"], "snooze_minutes", rcfg.snooze_minutes))
            except Exception:
                pass
            # Update logging level dynamically
            try:
                new_level_name = str(getattr(app_state["cfg"], "log_level", "INFO")).upper()
                new_level = getattr(logging, new_level_name, logging.INFO)
                root_logger = logging.getLogger()
                root_logger.setLevel(new_level)
                for h in list(root_logger.handlers):
                    try:
                        h.setLevel(new_level)
                    except Exception:
                        pass
                log.info("Applied new log level: %s", new_level_name)
            except Exception:
                pass
            log.info("Settings updated and applied")
    settings_action.triggered.connect(open_settings)

    # Pause/resume action
    pause_action = QAction("Pause polling", menu)
    def toggle_pause():
        state["paused"] = not state["paused"]
        if state["paused"]:
            pause_action.setText("Resume polling")
            log.info("Polling paused by user")
        else:
            pause_action.setText("Pause polling")
            log.info("Polling resumed by user")
    pause_action.triggered.connect(toggle_pause)

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
        menu.insertAction(actions[0], settings_action)
        menu.insertAction(actions[0], pause_action)
        menu.insertAction(actions[0], snooze_action)
    else:
        menu.addAction(open_action)
        menu.addAction(settings_action)
        menu.addAction(pause_action)
        menu.addAction(snooze_action)

    # Log on lock/unlock
    watcher.session_locked.connect(lambda: log.info("System locked: polling suspended"))
    watcher.session_unlocked.connect(lambda: log.info("System unlocked: polling resumed"))

    # Define the polling function
    def poll_once() -> None:
        # Skip polling when session is locked or user paused
        try:
            if state["paused"] or not watcher.is_unlocked():
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
