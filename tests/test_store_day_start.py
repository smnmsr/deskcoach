from __future__ import annotations

import sqlite3
from datetime import datetime


def test_update_aggregate_uses_configured_day_start(tmp_path, monkeypatch):
    from deskcoach.models import store

    dbfile = tmp_path / "deskcoach.db"
    monkeypatch.setattr(store, "db_path", lambda: dbfile)
    store.init_db()

    now = int(datetime(2025, 1, 2, 3, 30, 0).timestamp())
    store.save_measurement(now - 300, 800)

    store.update_daily_aggregates_now(
        stand_threshold_mm=900,
        now_ts=now,
        start_of_day_hour=4,
    )

    with sqlite3.connect(dbfile) as conn:
        rows = conn.execute("SELECT date FROM daily_aggregates ORDER BY date ASC").fetchall()

    assert rows == [("2025-01-01",)]


def test_day_bounds_roll_to_previous_date_before_start_hour():
    from deskcoach.models import store

    now = int(datetime(2025, 1, 2, 1, 15, 0).timestamp())
    start_ts, date_str = store._day_bounds_local(now, start_of_day_hour=4)

    start_dt = datetime.fromtimestamp(start_ts)
    assert date_str == "2025-01-01"
    assert start_dt.hour == 4
    assert start_dt.day == 1
