from __future__ import annotations

from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QPushButton
from PyQt6.QtCore import QTimer
from pathlib import Path

from .settings_dialog import SettingsDialog
from ..models import store


class MainWindow(QMainWindow):
    """MainWindow extracted from main.py to live under views/.

    It shows a simple central widget with a button to open SettingsDialog.
    """

    def __init__(self, cfg_ns) -> None:
        super().__init__()
        self.setWindowTitle("DeskCoach")
        self._cfg_ns = cfg_ns
        central = QWidget(self)
        v = QVBoxLayout(central)

        # Stats display (use a disabled flat button to avoid QLabel dependency in tests)
        self._stats_btn = QPushButton("", central)
        try:
            self._stats_btn.setEnabled(False)
            self._stats_btn.setFlat(True)
        except Exception:
            pass
        v.addWidget(self._stats_btn)

        # Settings
        btn = QPushButton("Settings…", central)
        btn.clicked.connect(self.open_settings)
        v.addWidget(btn)

        # Button to open data folder (database and logs)
        btn_open_folder = QPushButton("Open data folder", central)
        btn_open_folder.clicked.connect(self.open_data_folder)
        v.addWidget(btn_open_folder)

        self.setCentralWidget(central)

        # Periodic refresh of stats
        self._stats_timer = QTimer(self)
        self._stats_timer.setInterval(60_000)  # 60s
        self._stats_timer.timeout.connect(self.refresh_stats)
        self._stats_timer.start()
        # Initial populate
        self.refresh_stats()

    def open_settings(self) -> None:
        dlg = SettingsDialog(self, self._cfg_ns)
        dlg.exec()

    def open_data_folder(self) -> None:
        try:
            from PyQt6.QtGui import QDesktopServices
            from PyQt6.QtCore import QUrl
            folder = store.db_path().parent
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        except Exception:
            pass

    def _fmt_hm(self, seconds: int) -> str:
        m = max(0, int(seconds)) // 60
        h = m // 60
        mm = m % 60
        return f"{h}h{mm:02d}"

    def refresh_stats(self) -> None:
        try:
            stand_thr = int(getattr(self._cfg_ns.app, "stand_threshold_mm", 900))
            today_sit, today_stand = store.get_today_aggregates(stand_thr)
            y_sit, y_stand = store.get_yesterday_aggregates_until_same_time(stand_thr)
        except Exception:
            # If anything goes wrong, don't crash the UI
            txt = "Today\nStanding —\nSitting —"
            try:
                self._stats_btn.setText(txt)
            except Exception:
                pass
            return
        # Standing comparison
        comp_text = ""
        if y_stand > 0:
            delta_pct = int(round((today_stand - y_stand) * 100 / y_stand))
            if delta_pct > 0:
                comp_text = f" ({delta_pct}% more than yesterday at the same time)"
            elif delta_pct < 0:
                comp_text = f" ({abs(delta_pct)}% less than yesterday at the same time)"
            else:
                comp_text = " (same as yesterday at the same time)"
        else:
            comp_text = ""
        txt = (
            "Today\n"
            f"Standing {self._fmt_hm(today_stand)}{comp_text}\n"
            f"Sitting {self._fmt_hm(today_sit)}"
        )
        try:
            self._stats_btn.setText(txt)
        except Exception:
            pass

    # Don’t quit the app when the main window is closed; just hide to tray
    def closeEvent(self, event: QCloseEvent) -> None:  # type: ignore[override]
        try:
            event.ignore()
        except Exception:
            pass
        self.hide()
