from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import (
    QDialog,
    QWidget,
    QFormLayout,
    QLineEdit,
    QDoubleSpinBox,
    QSpinBox,
    QMessageBox,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
)

# Optional widgets for minimal test stubs
try:  # pragma: no cover - exercised by import tests
    from PyQt6.QtWidgets import QLabel as _QLabel, QGroupBox as _QGroupBox  # type: ignore
    QLabel = _QLabel  # type: ignore
    QGroupBox = _QGroupBox  # type: ignore
except Exception:  # pragma: no cover
    QLabel = QWidget  # type: ignore
    QGroupBox = QWidget  # type: ignore


class SettingsDialog(QDialog):
    """Application settings dialog.

    Extracted from main.py to keep UI code under views/.
    Expects a config namespace object with an `.app` attribute.
    """

    def __init__(self, parent: Optional[QWidget], cfg_ns) -> None:
        super().__init__(parent)
        self.setWindowTitle("DeskCoach Settings")
        # Make the window comfortably wide so long URLs fit
        self.setMinimumWidth(640)
        self.resize(720, 640)

        self._cfg_ns = cfg_ns  # SimpleNamespace with .app
        appcfg = cfg_ns.app

        main = QVBoxLayout(self)

        # Connectivity section
        conn_box = QGroupBox("Connectivity")
        conn_form = QFormLayout(conn_box)
        conn_help = QLabel("Where DeskCoach connects to fetch desk posture/height data. Use the full base URL of your watcher service.")
        conn_help.setWordWrap(True)
        conn_form.addRow(conn_help)

        self.base_url = QLineEdit(str(getattr(appcfg, "base_url", "")))
        self.base_url.setPlaceholderText("https://example.your-watcher.local")
        self.base_url.setToolTip("Base address of the desk watcher service that provides current height and history.")
        self.poll_minutes = QDoubleSpinBox()
        self.poll_minutes.setRange(0.01, 1440.0)
        self.poll_minutes.setDecimals(2)
        self.poll_minutes.setValue(float(getattr(appcfg, "poll_minutes", 5)))
        self.poll_minutes.setToolTip("How often to poll the service for new data.")
        conn_form.addRow("Base URL", self.base_url)
        conn_form.addRow("Poll interval (minutes)", self.poll_minutes)
        main.addWidget(conn_box)

        # Goals & thresholds
        goal_box = QGroupBox("Goals & thresholds")
        goal_form = QFormLayout(goal_box)
        goal_help = QLabel("Configure when DeskCoach considers you standing and your daily standing goal.")
        goal_help.setWordWrap(True)
        goal_form.addRow(goal_help)

        self.stand_threshold_mm = QSpinBox()
        self.stand_threshold_mm.setRange(300, 2000)
        self.stand_threshold_mm.setValue(int(getattr(appcfg, "stand_threshold_mm", 900)))
        self.stand_threshold_mm.setToolTip("Desk height above which you are considered standing (in millimeters).")

        # Daily standing goal (hours)
        self.stand_goal_hours = QDoubleSpinBox()
        self.stand_goal_hours.setRange(0.0, 24.0)
        self.stand_goal_hours.setDecimals(1)
        try:
            goal_mm = int(getattr(appcfg, "stand_goal_mm", 240))
        except Exception:
            goal_mm = 240
        self.stand_goal_hours.setValue(max(0.0, float(goal_mm) / 60.0))
        self.stand_goal_hours.setToolTip("Target amount of time to spend standing each day (hours).")

        goal_form.addRow("Stand threshold (mm)", self.stand_threshold_mm)
        goal_form.addRow("Daily standing goal (hours)", self.stand_goal_hours)
        main.addWidget(goal_box)

        # Reminders section
        rem_box = QGroupBox("Reminders")
        rem_form = QFormLayout(rem_box)
        rem_help = QLabel("DeskCoach will remind you to stand after you've been sitting for a while. Configure the timing here.")
        rem_help.setWordWrap(True)
        rem_form.addRow(rem_help)

        self.remind_after_minutes = QSpinBox()
        self.remind_after_minutes.setRange(1, 600)
        self.remind_after_minutes.setValue(int(getattr(appcfg, "remind_after_minutes", 45)))
        self.remind_after_minutes.setToolTip("How long you can sit before the first stand reminder.")

        self.remind_repeat_minutes = QSpinBox()
        self.remind_repeat_minutes.setRange(1, 600)
        self.remind_repeat_minutes.setValue(int(getattr(appcfg, "remind_repeat_minutes", 5)))
        self.remind_repeat_minutes.setToolTip("How often to repeat the stand reminder until you stand or snooze.")

        self.snooze_minutes = QSpinBox()
        self.snooze_minutes.setRange(1, 600)
        self.snooze_minutes.setValue(int(getattr(appcfg, "snooze_minutes", 30)))
        self.snooze_minutes.setToolTip("Default snooze duration when you postpone a reminder.")

        rem_form.addRow("Remind after (minutes)", self.remind_after_minutes)
        rem_form.addRow("Repeat every (minutes)", self.remind_repeat_minutes)
        rem_form.addRow("Snooze default (minutes)", self.snooze_minutes)
        main.addWidget(rem_box)

        # Standing checks section
        chk_box = QGroupBox("Standing checks")
        chk_form = QFormLayout(chk_box)
        chk_help = QLabel("After a reminder, DeskCoach checks if you're standing. These intervals control that verification.")
        chk_help.setWordWrap(True)
        chk_form.addRow(chk_help)

        self.standing_check_after_minutes = QSpinBox()
        self.standing_check_after_minutes.setRange(1, 600)
        self.standing_check_after_minutes.setValue(int(getattr(appcfg, "standing_check_after_minutes", 30)))
        self.standing_check_after_minutes.setToolTip("Wait this long after the reminder before checking if you're standing.")

        self.standing_check_repeat_minutes = QSpinBox()
        self.standing_check_repeat_minutes.setRange(1, 600)
        self.standing_check_repeat_minutes.setValue(int(getattr(appcfg, "standing_check_repeat_minutes", 30)))
        self.standing_check_repeat_minutes.setToolTip("If still not standing, repeat the check with this interval.")

        self.lock_reset_threshold_minutes = QSpinBox()
        self.lock_reset_threshold_minutes.setRange(0, 1440)
        self.lock_reset_threshold_minutes.setValue(int(getattr(appcfg, "lock_reset_threshold_minutes", 5)))
        self.lock_reset_threshold_minutes.setToolTip("If the computer was locked longer than this, the sit timer resets (minutes). Set 0 to disable.")

        chk_form.addRow("Standing check after (minutes)", self.standing_check_after_minutes)
        chk_form.addRow("Standing check repeat (minutes)", self.standing_check_repeat_minutes)
        chk_form.addRow("Lock reset threshold (minutes)", self.lock_reset_threshold_minutes)
        main.addWidget(chk_box)

        # Notifications section
        notif_box = QGroupBox("Notifications")
        notif_form = QFormLayout(notif_box)
        notif_help = QLabel("DeskCoach uses the system tray to show notifications. On Windows, they appear as native notifications.")
        notif_help.setWordWrap(True)
        notif_form.addRow(notif_help)

        # Test notification button to preview current settings and check system support
        try:
            from PyQt6.QtWidgets import QPushButton as _QPushButton, QSystemTrayIcon as _QSystemTrayIcon  # type: ignore
            test_btn = _QPushButton("Test notification")
            def _do_test():
                try:
                    # Check whether the platform supports tray messages
                    supports = False
                    try:
                        supports = bool(_QSystemTrayIcon.supportsMessages())
                    except Exception:
                        supports = False

                    # Provide user feedback
                    if supports:
                        QMessageBox.information(self, "Notifications supported", "Your system supports tray notifications. A test notification will be sent now.")
                    else:
                        QMessageBox.warning(self, "Notifications not supported", "Your system does not report support for tray notifications. DeskCoach may not be able to show reminder popups on this system. We'll still try using a fallback.")

                    # Lazy import to avoid hard dependency during tests
                    try:
                        from ..services import notifier as _notifier  # type: ignore
                    except Exception:
                        from deskcoach.services import notifier as _notifier  # type: ignore
                    _notifier.notify("DeskCoach test", "This is a test notification.")
                except Exception:
                    # Silent fail; we don't want the settings dialog to crash on test
                    pass
            test_btn.clicked.connect(_do_test)
            notif_form.addRow(test_btn)
        except Exception:
            pass

        main.addWidget(notif_box)

        # Logging section (separate from notifications)
        log_box = QGroupBox("Logging")
        log_form = QFormLayout(log_box)
        log_help = QLabel("Configure application logging verbosity. This does not affect notifications.")
        log_help.setWordWrap(True)
        log_form.addRow(log_help)

        # Log level selector (lazy import to allow tests without full PyQt6 widgets)
        try:
            from PyQt6.QtWidgets import QComboBox  # type: ignore
            self.log_level = QComboBox()
            self.log_level.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
            current_level = str(getattr(appcfg, "log_level", "INFO")).upper()
            idx = max(0, self.log_level.findText(current_level))
            self.log_level.setCurrentIndex(idx)
        except Exception:
            # Fallback placeholder when QComboBox is unavailable in minimal test stubs
            self.log_level = QWidget(self)

        log_form.addRow("Log level", self.log_level)
        main.addWidget(log_box)

        # Buttons row
        btn_row = QHBoxLayout()
        btn_save = QPushButton("Save")
        btn_cancel = QPushButton("Cancel")
        btn_save.clicked.connect(self._on_save)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_save)
        btn_row.addWidget(btn_cancel)
        main.addLayout(btn_row)

    def _on_save(self) -> None:
        try:
            # Persist to the user data config path used by config.load_config
            from ..config import get_user_config_path

            # Collect values
            base_url = self.base_url.text()
            poll_minutes = float(self.poll_minutes.value())
            stand_threshold_mm = int(self.stand_threshold_mm.value())
            remind_after_minutes = int(self.remind_after_minutes.value())
            remind_repeat_minutes = int(self.remind_repeat_minutes.value())
            standing_check_after_minutes = int(self.standing_check_after_minutes.value())
            standing_check_repeat_minutes = int(self.standing_check_repeat_minutes.value())
            snooze_minutes = int(self.snooze_minutes.value())
            lock_reset_threshold_minutes = int(self.lock_reset_threshold_minutes.value())
            # When QComboBox fallback is used (tests), currentText may be missing
            log_level = str(getattr(self.log_level, 'currentText', lambda: 'INFO')()).upper()
            stand_goal_mm = int(round(self.stand_goal_hours.value() * 60))

            cfg_text = (
                "[app]\n"
                f"base_url = \"{base_url}\"\n"
                f"poll_minutes = {poll_minutes}\n"
                f"stand_threshold_mm = {stand_threshold_mm}\n"
                f"remind_after_minutes = {remind_after_minutes}\n"
                f"remind_repeat_minutes = {remind_repeat_minutes}\n"
                f"standing_check_after_minutes = {standing_check_after_minutes}\n"
                f"standing_check_repeat_minutes = {standing_check_repeat_minutes}\n"
                f"snooze_minutes = {snooze_minutes}\n"
                f"lock_reset_threshold_minutes = {lock_reset_threshold_minutes}\n"
                f"log_level = \"{log_level}\"\n"
                f"stand_goal_mm = {stand_goal_mm}\n"
            )

            cfg_path = get_user_config_path()
            cfg_path.write_text(cfg_text, encoding="utf-8")

            # Update in-memory config namespace so the rest of the app reflects changes immediately
            try:
                appcfg = getattr(self._cfg_ns, 'app', None)
                if appcfg is not None:
                    appcfg.base_url = base_url
                    appcfg.poll_minutes = poll_minutes
                    appcfg.stand_threshold_mm = stand_threshold_mm
                    appcfg.remind_after_minutes = remind_after_minutes
                    appcfg.remind_repeat_minutes = remind_repeat_minutes
                    appcfg.standing_check_after_minutes = standing_check_after_minutes
                    appcfg.standing_check_repeat_minutes = standing_check_repeat_minutes
                    appcfg.snooze_minutes = snooze_minutes
                    appcfg.lock_reset_threshold_minutes = lock_reset_threshold_minutes
                    appcfg.log_level = log_level
                    # Note: stand_goal_mm is currently not part of SimpleNamespace in load_config
            except Exception:
                pass

            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save settings: {e}")
