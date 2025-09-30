from __future__ import annotations

from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QPushButton
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
        btn = QPushButton("Settings…", central)
        btn.clicked.connect(self.open_settings)
        v.addWidget(btn)

        # Button to open data folder (database and logs)
        btn_open_folder = QPushButton("Open data folder", central)
        btn_open_folder.clicked.connect(self.open_data_folder)
        v.addWidget(btn_open_folder)

        self.setCentralWidget(central)

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

    # Don’t quit the app when the main window is closed; just hide to tray
    def closeEvent(self, event: QCloseEvent) -> None:  # type: ignore[override]
        try:
            event.ignore()
        except Exception:
            pass
        self.hide()
