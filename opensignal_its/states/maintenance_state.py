"""Maintenance and runtime health state slice."""

from __future__ import annotations

from typing import Any

from ..services import MaintenanceService, OpsApiService, scheduler_status


def _runtime_health_snapshot_to_state_fields(
    sched: dict[str, Any],
    cleanup: dict[str, Any],
    ops_health: dict[str, Any],
) -> dict[str, Any]:
    retention_scheduler_enabled = bool(sched.get("enabled", False))
    retention_scheduler_running = bool(sched.get("running", False))
    interval = sched.get("interval_seconds")
    retention_scheduler_interval_text = str(interval) if interval is not None else "unknown"
    retention_scheduler_error = str(sched.get("error", "") or "")

    last_retention_cleanup_at = str(cleanup.get("last_run_at", ""))
    last_retention_cleanup_result = str(
        cleanup.get("message", "No retention cleanup run yet.")
    )

    scheduler_line = (
        f"Scheduler: {'enabled' if retention_scheduler_enabled else 'disabled'}, "
        f"{'running' if retention_scheduler_running else 'stopped'}, "
        f"interval={retention_scheduler_interval_text}s"
    )
    if retention_scheduler_error:
        scheduler_line = f"{scheduler_line} ({retention_scheduler_error})"

    cleanup_at = last_retention_cleanup_at if last_retention_cleanup_at else "never"
    storage = dict(ops_health.get("storage", {}))
    counts = dict(storage.get("table_row_counts", {}))
    runtime_storage_warning_rows = [str(row) for row in storage.get("warnings", [])]
    runtime_storage_alert_rows = [
        str(row) for row in storage.get("persistent_alerts", [])
    ]
    dispatch = dict(storage.get("alert_dispatch", {}))
    if dispatch:
        runtime_alert_dispatch_summary = (
            "Alert dispatch: "
            f"enabled={bool(dispatch.get('enabled', False))}, "
            f"sent={int(dispatch.get('sent', 0))}, "
            f"skipped={int(dispatch.get('skipped', 0))}, "
            f"failed={int(dispatch.get('failed', 0))}, "
            f"deadlettered={int(dispatch.get('deadlettered', 0))}."
        )
    else:
        runtime_alert_dispatch_summary = "Alert dispatch unavailable."

    if counts:
        ordered = ", ".join(f"{key}={int(value)}" for key, value in sorted(counts.items()))
        runtime_storage_summary = f"Storage row counts: {ordered}"
    else:
        runtime_storage_summary = "Storage row counts unavailable."

    storage_warning_text = (
        f" Storage warnings: {len(runtime_storage_warning_rows)}."
        if runtime_storage_warning_rows
        else " Storage warnings: none."
    )
    storage_alert_text = (
        f" Persistent alerts: {len(runtime_storage_alert_rows)}."
        if runtime_storage_alert_rows
        else " Persistent alerts: none."
    )
    runtime_health_notice = (
        f"{scheduler_line}. Last cleanup: {cleanup_at}. "
        f"{last_retention_cleanup_result}{storage_warning_text}{storage_alert_text}"
    )

    return {
        "retention_scheduler_enabled": retention_scheduler_enabled,
        "retention_scheduler_running": retention_scheduler_running,
        "retention_scheduler_interval_text": retention_scheduler_interval_text,
        "retention_scheduler_error": retention_scheduler_error,
        "last_retention_cleanup_at": last_retention_cleanup_at,
        "last_retention_cleanup_result": last_retention_cleanup_result,
        "runtime_storage_warning_rows": runtime_storage_warning_rows,
        "runtime_storage_alert_rows": runtime_storage_alert_rows,
        "runtime_alert_dispatch_summary": runtime_alert_dispatch_summary,
        "runtime_storage_summary": runtime_storage_summary,
        "runtime_health_notice": runtime_health_notice,
    }


class MaintenanceStateMixin:
    maintenance_notice: str = ""
    runtime_health_notice: str = "Runtime health not refreshed yet."
    runtime_storage_summary: str = "Storage health not refreshed yet."
    runtime_storage_warning_rows: list[str] = []
    runtime_storage_alert_rows: list[str] = []
    runtime_alert_dispatch_summary: str = "Alert dispatch idle."
    retention_scheduler_enabled: bool = False
    retention_scheduler_running: bool = False
    retention_scheduler_interval_text: str = "unknown"
    retention_scheduler_error: str = ""
    last_retention_cleanup_at: str = ""
    last_retention_cleanup_result: str = "No retention cleanup run yet."

    def run_retention_cleanup(self):
        if not self._is_role_authorized({"admin"}):
            self.maintenance_notice = "Retention cleanup denied: admin authentication required."
            self.error = self.maintenance_notice
            return
        try:
            MaintenanceService.run_retention_cleanup()
            cleanup = MaintenanceService.get_cleanup_status()
            self.maintenance_notice = str(
                cleanup.get("message", "Retention cleanup complete.")
            )
            self.error = ""
        except Exception as exc:
            self.maintenance_notice = f"Retention cleanup failed: {exc}"
            self.error = self.maintenance_notice
        self.refresh_runtime_health()

    def refresh_runtime_health(self):
        adapted = _runtime_health_snapshot_to_state_fields(
            scheduler_status(),
            MaintenanceService.get_cleanup_status(),
            OpsApiService.health_snapshot(),
        )
        self.retention_scheduler_enabled = adapted["retention_scheduler_enabled"]
        self.retention_scheduler_running = adapted["retention_scheduler_running"]
        self.retention_scheduler_interval_text = adapted["retention_scheduler_interval_text"]
        self.retention_scheduler_error = adapted["retention_scheduler_error"]
        self.last_retention_cleanup_at = adapted["last_retention_cleanup_at"]
        self.last_retention_cleanup_result = adapted["last_retention_cleanup_result"]
        self.runtime_storage_warning_rows = adapted["runtime_storage_warning_rows"]
        self.runtime_storage_alert_rows = adapted["runtime_storage_alert_rows"]
        self.runtime_alert_dispatch_summary = adapted["runtime_alert_dispatch_summary"]
        self.runtime_storage_summary = adapted["runtime_storage_summary"]
        self.runtime_health_notice = adapted["runtime_health_notice"]