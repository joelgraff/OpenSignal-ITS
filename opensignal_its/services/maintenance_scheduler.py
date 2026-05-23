"""Optional scheduler for periodic retention cleanup."""

from __future__ import annotations

import os
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler

from .maintenance_service import MaintenanceService


_scheduler: BackgroundScheduler | None = None


def _is_enabled() -> bool:
    raw = os.getenv("OPENSIGNAL_ENABLE_RETENTION_SCHEDULER", "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _interval_seconds() -> int:
    raw = os.getenv("OPENSIGNAL_RETENTION_SCHEDULE_SECONDS", "3600").strip()
    try:
        parsed = int(raw)
    except ValueError as exc:
        raise ValueError(f"OPENSIGNAL_RETENTION_SCHEDULE_SECONDS must be an integer, got: {raw!r}") from exc
    if parsed < 300:
        raise ValueError("OPENSIGNAL_RETENTION_SCHEDULE_SECONDS must be >= 300")
    return parsed


def _run_retention_job() -> tuple[int, int]:
    return MaintenanceService.run_retention_cleanup()


def start_retention_scheduler() -> tuple[bool, str]:
    """Start periodic retention cleanup scheduler if enabled."""
    global _scheduler

    if not _is_enabled():
        return False, "Retention scheduler disabled by configuration."

    if _scheduler is not None:
        return True, "Retention scheduler already running."

    interval = _interval_seconds()
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        _run_retention_job,
        trigger="interval",
        seconds=interval,
        id="retention_cleanup",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    _scheduler = scheduler
    return True, f"Retention scheduler started with interval {interval}s."


def stop_retention_scheduler() -> tuple[bool, str]:
    """Stop scheduler; primarily used by tests."""
    global _scheduler
    if _scheduler is None:
        return False, "Retention scheduler not running."
    _scheduler.shutdown(wait=False)
    _scheduler = None
    return True, "Retention scheduler stopped."


def scheduler_status() -> dict[str, Any]:
    interval_seconds = None
    error = ""
    if _is_enabled():
        try:
            interval_seconds = _interval_seconds()
        except ValueError as exc:
            error = str(exc)

    return {
        "enabled": _is_enabled(),
        "running": _scheduler is not None,
        "interval_seconds": interval_seconds,
        "error": error,
    }
