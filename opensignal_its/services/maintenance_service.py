"""Operational maintenance service helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Any

from ..db import STORE


_status_lock = Lock()
_last_cleanup_status: dict[str, Any] = {
    "last_run_at": "",
    "ok": False,
    "message": "No retention cleanup run yet.",
    "deleted_commands": 0,
    "deleted_snapshots": 0,
    "deleted_alarm_silences": 0,
    "deleted_alarm_events": 0,
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class MaintenanceService:
    """Maintenance operations that can be run at startup or on demand."""

    @staticmethod
    def run_retention_cleanup() -> tuple[int, int]:
        try:
            deleted_commands, deleted_snapshots = STORE.apply_retention_from_env()
            deleted_alarm_silences = STORE.purge_expired_alarm_silences()
            deleted_alarm_events = STORE.apply_alarm_event_retention_from_env()
        except Exception as exc:
            with _status_lock:
                _last_cleanup_status.update(
                    {
                        "last_run_at": _utc_now_iso(),
                        "ok": False,
                        "message": f"Retention cleanup failed: {exc}",
                        "deleted_commands": 0,
                        "deleted_snapshots": 0,
                        "deleted_alarm_silences": 0,
                        "deleted_alarm_events": 0,
                    }
                )
            raise

        with _status_lock:
            _last_cleanup_status.update(
                {
                    "last_run_at": _utc_now_iso(),
                    "ok": True,
                    "message": (
                        "Retention cleanup complete. "
                        f"Commands deleted: {deleted_commands}, "
                        f"snapshots deleted: {deleted_snapshots}, "
                        f"expired alarm silences deleted: {deleted_alarm_silences}, "
                        f"alarm events deleted: {deleted_alarm_events}."
                    ),
                    "deleted_commands": deleted_commands,
                    "deleted_snapshots": deleted_snapshots,
                    "deleted_alarm_silences": deleted_alarm_silences,
                    "deleted_alarm_events": deleted_alarm_events,
                }
            )
        return deleted_commands, deleted_snapshots

    @staticmethod
    def get_cleanup_status() -> dict[str, Any]:
        with _status_lock:
            return dict(_last_cleanup_status)
