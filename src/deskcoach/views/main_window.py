from __future__ import annotations

from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QPushButton, QHBoxLayout, QMessageBox
from PyQt6.QtCore import QTimer, Qt
from pathlib import Path

# Optional widgets (not present in minimal test stubs)
try:  # pragma: no cover - exercised by import tests
    from PyQt6.QtWidgets import QProgressBar as _QProgressBar, QFrame as _QFrame, QProgressDialog as _QProgressDialog, QLabel as _QLabel  # type: ignore
    QProgressBar = _QProgressBar  # type: ignore
    QFrame = _QFrame  # type: ignore
    QProgressDialog = _QProgressDialog  # type: ignore
    QLabel = _QLabel  # type: ignore
except Exception:  # pragma: no cover
    QProgressBar = QWidget  # type: ignore
    QFrame = QWidget  # type: ignore
    QProgressDialog = QWidget  # type: ignore
    QLabel = QWidget  # type: ignore

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

        # Header with date and optional streak
        self._header = QWidget(central)
        header_layout = QHBoxLayout(self._header)
        try:
            header_layout.setContentsMargins(0, 0, 0, 0)
        except Exception:
            pass
        self._date_lbl = QLabel("Today", self._header)
        try:
            self._date_lbl.setProperty("dc", "date")
        except Exception:
            pass
        self._streak_lbl = QLabel("", self._header)
        try:
            self._streak_lbl.setVisible(False)
            self._streak_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._streak_lbl.setProperty("dc", "pill")
        except Exception:
            pass
        try:
            header_layout.addWidget(self._date_lbl)
            header_layout.addStretch(1)
            header_layout.addWidget(self._streak_lbl)
        except Exception:
            pass
        v.addWidget(self._header)

        # Summary pill before cards
        self._summary_pill = QLabel("", central)
        try:
            self._summary_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._summary_pill.setProperty("dc", "pill")
            self._summary_pill.setVisible(False)
        except Exception:
            pass
        v.addWidget(self._summary_pill)

        # Cards row (Standing / Sitting)
        self._cards = QWidget(central)
        cards_layout = QHBoxLayout(self._cards)
        try:
            cards_layout.setContentsMargins(0, 0, 0, 0)
        except Exception:
            pass
        self._stand_card = self._create_stat_card(title="Standing")
        self._sit_card = self._create_stat_card(title="Sitting")
        try:
            cards_layout.addWidget(self._stand_card)
            cards_layout.addSpacing(8)
            cards_layout.addWidget(self._sit_card)
        except Exception:
            pass
        v.addWidget(self._cards)

        # Goal progress (standing time vs daily goal)
        self._goal_prog = QProgressBar(central)
        try:
            self._goal_prog.setMinimum(0)
            self._goal_prog.setMaximum(100)
            self._goal_prog.setValue(0)
            self._goal_prog.setTextVisible(True)
            self._goal_prog.setVisible(False)
        except Exception:
            pass
        v.addWidget(self._goal_prog)

        # Tip/message area
        self._tip_lbl = QLabel("", central)
        try:
            self._tip_lbl.setWordWrap(True)
            self._tip_lbl.setProperty("dc", "muted")
        except Exception:
            pass
        v.addWidget(self._tip_lbl)

        # Settings
        btn = QPushButton("Settings…", central)
        btn.clicked.connect(self.open_settings)
        v.addWidget(btn)

        # Button to open data folder (database and logs)
        btn_open_folder = QPushButton("Open data folder", central)
        btn_open_folder.clicked.connect(self.open_data_folder)
        v.addWidget(btn_open_folder)

        # Recalculate aggregates
        self._btn_recalc = QPushButton("Recalculate aggregated counts", central)
        try:
            self._btn_recalc.clicked.connect(self._on_recalc_clicked)
        except Exception:
            pass
        v.addWidget(self._btn_recalc)

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

    def _create_stat_card(self, title: str) -> QWidget:
        w = QFrame(self)
        try:
            w.setFrameShape(QFrame.Shape.StyledPanel)
            w.setProperty("dc", "card")
        except Exception:
            pass
        lay = QVBoxLayout(w)
        try:
            lay.setContentsMargins(12, 12, 12, 12)
        except Exception:
            pass
        title_lbl = QLabel(title, w)
        try:
            title_lbl.setProperty("dc", "cardTitle")
        except Exception:
            pass
        value_lbl = QLabel("—", w)
        try:
            value_lbl.setProperty("dc", "value")
        except Exception:
            pass
        subrow = QWidget(w)
        sublay = QHBoxLayout(subrow)
        try:
            sublay.setContentsMargins(0, 0, 0, 0)
        except Exception:
            pass
        trend_lbl = QLabel("", subrow)
        try:
            trend_lbl.setVisible(False)
            trend_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            trend_lbl.setProperty("dc", "pill")
        except Exception:
            pass
        try:
            sublay.addWidget(trend_lbl)
            sublay.addStretch(1)
        except Exception:
            pass
        prog = QProgressBar(w)
        try:
            prog.setMinimum(0)
            prog.setMaximum(100)
            prog.setValue(0)
            prog.setTextVisible(True)
        except Exception:
            pass
        try:
            lay.addWidget(title_lbl)
            lay.addWidget(value_lbl)
            lay.addWidget(subrow)
            lay.addWidget(prog)
        except Exception:
            pass
        # Expose parts for refresh
        w.title_lbl = title_lbl  # type: ignore[attr-defined]
        w.value_lbl = value_lbl  # type: ignore[attr-defined]
        w.trend_lbl = trend_lbl  # type: ignore[attr-defined]
        w.progress = prog        # type: ignore[attr-defined]
        return w

    def _fmt_hm(self, seconds: int) -> str:
        m = max(0, int(seconds)) // 60
        h, mm = divmod(m, 60)
        return f"{h}h{mm:02d}"

    def _goal_minutes(self) -> int:
        try:
            return int(getattr(self._cfg_ns.app, "stand_goal_mm", 240))
        except Exception:
            return 240

    def _streak_days(self) -> int | None:
        # Placeholder until backend provides a real streak
        return None

    def _trend_label_pct(self, today_pct: int, yday_pct: int, invert_good: bool = False) -> tuple[str, str | None]:
        """Return (text, class) comparing today's percentage vs yesterday's.
        Text expresses percentage points more/less than yesterday.

        Parameters
        ----------
        invert_good: bool
            When True, positive delta is considered bad (used for Sitting),
            and negative delta is considered good.
        """
        try:
            if yday_pct < 0:
                return ("", None)
            delta = int(today_pct) - int(yday_pct)
            if delta == 0:
                return ("Same as yesterday", None)
            if invert_good:
                # For sitting: more sitting than yesterday is bad
                if delta > 0:
                    return (f"{delta}% more than yesterday", "bad")
                else:
                    return (f"{abs(delta)}% less than yesterday", "good")
            else:
                if delta > 0:
                    return (f"{delta}% more than yesterday", "good")
                else:
                    return (f"{abs(delta)}% less than yesterday", "bad")
        except Exception:
            return ("", None)

    def _apply_pill(self, lbl: QLabel, text: str, klass: str | None) -> None:
        try:
            lbl.setText(text)
            lbl.setVisible(bool(text))
            # Tooltip to explain how comparison is computed
            if text:
                lbl.setToolTip(
                    "Compared to yesterday (full day). Based on precomputed daily aggregates; "
                    "no on-the-fly calculation. Session-locked time is excluded."
                )
            else:
                lbl.setToolTip("")
            lbl.setProperty("class", "")
            if klass:
                lbl.setProperty("class", klass)
            # Re-polish to apply dynamic property changes
            try:
                st = lbl.style()
                if st is not None:
                    st.unpolish(lbl)
                    st.polish(lbl)
            except Exception:
                pass
        except Exception:
            pass

    def _tip_for_balance(self, stand_pct: int) -> str:
        """Micro-coaching copy geared to the 50/50 goal (standing > sitting)."""
        try:
            if stand_pct >= 60:
                return "Great balance today! Consider a short walk to keep momentum."
            if stand_pct >= 50:
                return "Nice! You've beaten sitting. A few more stand moments keep the edge."
            if stand_pct >= 40:
                return "You're close to beating sitting — a 10 min stand session can tip it."
            return "Try a 5–10 min standing break now to move toward a better balance."
        except Exception:
            return ""

    def _set_empty_state(self) -> None:
        try:
            self._date_lbl.setText("Today")
        except Exception:
            pass
        for card in (self._stand_card, self._sit_card):
            try:
                card.value_lbl.setText("—")
                card.trend_lbl.setVisible(False)
                card.progress.setVisible(False)
            except Exception:
                pass

    def _on_recalc_clicked(self) -> None:
        try:
            stand_thr = int(getattr(self._cfg_ns.app, "stand_threshold_mm", 900))
        except Exception:
            stand_thr = 900
        # Confirm
        try:
            res = QMessageBox.question(
                self,
                "Recalculate aggregated counts",
                "This will clear cached daily aggregates and recompute them. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
        except Exception:
            res = QMessageBox.StandardButton.Yes  # non-interactive fallback
        if res != QMessageBox.StandardButton.Yes:
            return
        # Busy dialog
        dlg = None
        try:
            dlg = QProgressDialog("Recalculating…", None, 0, 0, self)
            dlg.setWindowTitle("Please wait")
            dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
            dlg.setMinimumDuration(0)
            dlg.setValue(0)
        except Exception:
            dlg = None
        # Run in background thread
        import threading
        done_flag = {"done": False}

        def _work():
            try:
                store.clear_daily_aggregates()
                store.backfill_past_aggregates(stand_thr)
                store.update_daily_aggregates_now(stand_thr)
            except Exception:
                pass
            finally:
                done_flag["done"] = True

        threading.Thread(target=_work, daemon=True).start()

        # Poll for completion
        def _check_done():
            if done_flag["done"]:
                try:
                    if dlg is not None:
                        dlg.close()
                except Exception:
                    pass
                self.refresh_stats()
            else:
                QTimer.singleShot(150, _check_done)

        QTimer.singleShot(150, _check_done)

    def refresh_stats(self) -> None:
        try:
            stand_thr = int(getattr(self._cfg_ns.app, "stand_threshold_mm", 900))
            # One-time backfill of past days to avoid on-the-fly comparisons
            if not hasattr(self, "_backfill_done") or not self._backfill_done:
                try:
                    store.backfill_past_aggregates(stand_thr)
                except Exception:
                    pass
                self._backfill_done = True
            today_sit, today_stand = store.get_today_aggregates(stand_thr)
            y_sit, y_stand = store.get_yesterday_full_aggregate(stand_thr)
        except Exception:
            # If anything goes wrong, don't crash the UI
            self._set_empty_state()
            return

        # Header: date and streak
        try:
            from datetime import datetime
            self._date_lbl.setText(datetime.now().strftime("%a, %b %d"))
            streak = self._streak_days()
            self._streak_lbl.setVisible(bool(streak))
            if streak:
                self._streak_lbl.setText(f"Streak: {streak} days")
        except Exception:
            pass

        # Compute percentages for comparison (standing share of the day)
        try:
            today_total = max(0, int(today_sit) + int(today_stand))
            y_total = max(0, int(y_sit) + int(y_stand))
            today_stand_pct = int(round((int(today_stand) * 100) / max(1, today_total)))
            y_stand_pct = int(round((int(y_stand) * 100) / max(1, y_total)))
            today_sit_pct = 100 - today_stand_pct if today_total > 0 else 0
            y_sit_pct = 100 - y_stand_pct if y_total > 0 else 0
        except Exception:
            today_stand_pct = 0
            y_stand_pct = 0
            today_sit_pct = 0
            y_sit_pct = 0

        # Summary pill (overall vs yesterday based on standing share)
        try:
            sum_text, sum_class = self._trend_label_pct(today_stand_pct, y_stand_pct)
            if sum_text:
                text = sum_text.replace("more than yesterday", "more than yesterday").replace("less than yesterday", "less than yesterday")
            else:
                text = ""
            if text:
                # Friendlier: "You're standing X% more/less than yesterday."
                text = text.replace("% ", "% ")
                text = text.replace("Same as yesterday", "Same as yesterday")
            self._apply_pill(self._summary_pill, ("You're standing " + text) if text else "", sum_class)
        except Exception:
            pass

        # Standing card
        try:
            self._stand_card.value_lbl.setText(self._fmt_hm(today_stand))
            # Remove trend pill inside cards per requirements
            self._stand_card.trend_lbl.setVisible(False)
            # Remove progress based on percentage inside card; keep card progress hidden
            self._stand_card.progress.setVisible(False)
        except Exception:
            pass

        # Sitting card
        try:
            self._sit_card.value_lbl.setText(self._fmt_hm(today_sit))
            self._sit_card.progress.setVisible(False)
            self._sit_card.trend_lbl.setVisible(False)
        except Exception:
            pass

        # Goal progress bar (standing time vs goal)
        try:
            goal_mm = self._goal_minutes()
            goal_sec = max(1, int(goal_mm) * 60)
            pct = int(min(100, (int(today_stand) * 100) // goal_sec))
            self._goal_prog.setVisible(True)
            self._goal_prog.setValue(pct)
            if today_stand >= goal_sec:
                self._goal_prog.setFormat("Standing goal reached! 🎉")
            else:
                self._goal_prog.setFormat(f"Standing goal: {self._fmt_hm(today_stand)} / {self._fmt_hm(goal_sec)} ({pct}%)")
        except Exception:
            pass

        # Tip
        try:
            self._tip_lbl.setText(self._tip_for_balance(today_stand_pct))
        except Exception:
            pass

    # Don’t quit the app when the main window is closed; just hide to tray
    def closeEvent(self, event: QCloseEvent) -> None:  # type: ignore[override]
        try:
            event.ignore()
        except Exception:
            pass
        self.hide()
