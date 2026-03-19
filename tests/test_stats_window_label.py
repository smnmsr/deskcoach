from __future__ import annotations

from datetime import datetime

from deskcoach.utils.time_stats import format_stats_window


def test_stats_window_label_for_same_day_window():
    now = datetime(2025, 1, 2, 10, 30, 0)
    label, tooltip = format_stats_window(now, start_of_day_hour=4)

    assert label == "Stats window: 04:00 -> now"
    assert "starts at 04:00" in tooltip
    assert "previous date" in tooltip


def test_stats_window_label_marks_previous_day_before_start_hour():
    now = datetime(2025, 1, 2, 1, 15, 0)
    label, _ = format_stats_window(now, start_of_day_hour=4)

    assert label == "Stats window: 04:00 -> now (previous day: Wed, Jan 01)"
