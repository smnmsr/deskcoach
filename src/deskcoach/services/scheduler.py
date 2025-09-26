"""Simple scheduler wrapper using APScheduler.

This module exposes a BackgroundScheduler instance and a helper to schedule
periodic jobs. Not used by main.py yet, but ready for future use.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Callable, Any

from apscheduler.schedulers.background import BackgroundScheduler

_scheduler: BackgroundScheduler | None = None


def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(timezone="UTC")
        _scheduler.start()
    return _scheduler


def schedule_every(interval: timedelta, func: Callable[..., Any], *, id: str | None = None, **kwargs: Any) -> None:
    """Schedule a function to run every `interval` using APScheduler."""
    seconds = interval.total_seconds()
    scheduler = get_scheduler()
    scheduler.add_job(func, "interval", seconds=seconds, id=id, replace_existing=True, kwargs=kwargs)


def shutdown_scheduler() -> None:
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
