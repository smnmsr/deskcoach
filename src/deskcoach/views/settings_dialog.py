from __future__ import annotations

from typing import Optional
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog,
    QWidget,
    QFormLayout,
    QLineEdit,
    QDoubleSpinBox,
    QSpinBox,
    QCheckBox,
    QMessageBox,
    QHBoxLayout,
    QPushButton,
)


class SettingsDialog(QDialog):
    """Application settings dialog.

    Extracted from main.py to keep UI code under views/.
    Expects a config namespace object with an `.app` attribute.
    """

    def __init__(self, parent: Optional[QWidget], cfg_ns) -> None:
        super().__init__(parent)
        self.setWindowTitle("DeskCoach Settings")
        self._cfg_ns = cfg_ns  # SimpleNamespace with .app
        appcfg = cfg_ns.app

        layout = QFormLayout(self)

        self.base_url = QLineEdit(str(getattr(appcfg, "base_url", "")))
        self.poll_minutes = QDoubleSpinBox()
        self.poll_minutes.setRange(0.01, 1440.0)
        self.poll_minutes.setDecimals(2)
        self.poll_minutes.setValue(float(getattr(appcfg, "poll_minutes", 5)))

        self.stand_threshold_mm = QSpinBox()
        self.stand_threshold_mm.setRange(300, 2000)
        self.stand_threshold_mm.setValue(int(getattr(appcfg, "stand_threshold_mm", 900)))

        self.remind_after_minutes = QSpinBox()
        self.remind_after_minutes.setRange(1, 600)
        self.remind_after_minutes.setValue(int(getattr(appcfg, "remind_after_minutes", 45)))

        self.remind_repeat_minutes = QSpinBox()
        self.remind_repeat_minutes.setRange(1, 600)
        self.remind_repeat_minutes.setValue(int(getattr(appcfg, "remind_repeat_minutes", 5)))

        self.standing_check_after_minutes = QSpinBox()
        self.standing_check_after_minutes.setRange(1, 600)
        self.standing_check_after_minutes.setValue(int(getattr(appcfg, "standing_check_after_minutes", 30)))

        self.standing_check_repeat_minutes = QSpinBox()
        self.standing_check_repeat_minutes.setRange(1, 600)
        self.standing_check_repeat_minutes.setValue(int(getattr(appcfg, "standing_check_repeat_minutes", 30)))

        self.snooze_minutes = QSpinBox()
        self.snooze_minutes.setRange(1, 600)
        self.snooze_minutes.setValue(int(getattr(appcfg, "snooze_minutes", 30)))

        self.lock_reset_threshold_minutes = QSpinBox()
        self.lock_reset_threshold_minutes.setRange(0, 1440)
        self.lock_reset_threshold_minutes.setValue(int(getattr(appcfg, "lock_reset_threshold_minutes", 5)))

        self.play_sound = QCheckBox("Play sound in notifications")
        self.play_sound.setChecked(bool(getattr(appcfg, "play_sound", True)))

        self.use_windows_toast = QCheckBox("Use Windows Toast notifications")
        self.use_windows_toast.setChecked(bool(getattr(appcfg, "use_windows_toast", True)))

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

        layout.addRow("Base URL", self.base_url)
        layout.addRow("Poll interval (minutes)", self.poll_minutes)
        layout.addRow("Stand threshold (mm)", self.stand_threshold_mm)
        layout.addRow("Remind after (minutes)", self.remind_after_minutes)
        layout.addRow("Repeat every (minutes)", self.remind_repeat_minutes)
        layout.addRow("Standing check after (minutes)", self.standing_check_after_minutes)
        layout.addRow("Standing check repeat (minutes)", self.standing_check_repeat_minutes)
        layout.addRow("Snooze default (minutes)", self.snooze_minutes)
        layout.addRow("Lock reset threshold (minutes)", self.lock_reset_threshold_minutes)
        layout.addRow("Log level", self.log_level)
        layout.addRow(self.play_sound)
        layout.addRow(self.use_windows_toast)

        # Buttons
        btn_row = QHBoxLayout()
        btn_save = QPushButton("Save")
        btn_cancel = QPushButton("Cancel")
        btn_save.clicked.connect(self._on_save)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_save)
        btn_row.addWidget(btn_cancel)
        layout.addRow(btn_row)

    def _on_save(self) -> None:
        try:
            # Persist to config.toml (project root)
            cfg_text = (
                "[app]\n"
                f"base_url = \"{self.base_url.text()}\"\n"
                f"poll_minutes = {float(self.poll_minutes.value())}\n"
                f"stand_threshold_mm = {int(self.stand_threshold_mm.value())}\n"
                f"remind_after_minutes = {int(self.remind_after_minutes.value())}\n"
                f"remind_repeat_minutes = {int(self.remind_repeat_minutes.value())}\n"
                f"standing_check_after_minutes = {int(self.standing_check_after_minutes.value())}\n"
                f"standing_check_repeat_minutes = {int(self.standing_check_repeat_minutes.value())}\n"
                f"snooze_minutes = {int(self.snooze_minutes.value())}\n"
                f"lock_reset_threshold_minutes = {int(self.lock_reset_threshold_minutes.value())}\n"
                f"play_sound = {'true' if self.play_sound.isChecked() else 'false'}\n"
                f"use_windows_toast = {'true' if self.use_windows_toast.isChecked() else 'false'}\n"
                f"log_level = \"{getattr(self.log_level, 'currentText', lambda: 'INFO')()}\"\n"
            )
            cfg_path = Path(__file__).resolve().parents[3] / "config.toml"
            cfg_path.write_text(cfg_text, encoding="utf-8")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save settings: {e}")
