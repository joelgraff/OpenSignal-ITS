"""Read-only operational API payload helpers."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..db import STORE
from .alert_dispatch_service import AlertDispatchService
from .event_service import EventService
from .maintenance_scheduler import scheduler_status
from .maintenance_service import MaintenanceService
from .polling_service import PollingService
from .secret_service import any_secret_matches, parse_secret_values


_warning_streaks: dict[str, int] = {}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class OpsApiService:
    """Builds serializable snapshots for operational API endpoints."""

    @staticmethod
    def _bool_env(name: str, default: bool) -> bool:
        raw = os.getenv(name, "true" if default else "false").strip().lower()
        return raw in {"1", "true", "yes", "on"}

    @staticmethod
    def ops_api_enabled() -> bool:
        return OpsApiService._bool_env("OPENSIGNAL_OPS_API_ENABLED", True)

    @staticmethod
    def required_api_token_values() -> list[str]:
        values: list[str] = []
        if os.getenv("OPENSIGNAL_OPS_API_TOKEN", "").strip():
            values.extend(parse_secret_values(os.getenv("OPENSIGNAL_OPS_API_TOKEN", "")))
        if os.getenv("OPENSIGNAL_OPS_API_TOKEN_HASH", "").strip():
            values.extend(parse_secret_values(os.getenv("OPENSIGNAL_OPS_API_TOKEN_HASH", "")))
        if os.getenv("OPENSIGNAL_OPS_API_TOKEN_HASHES", "").strip():
            values.extend(parse_secret_values(os.getenv("OPENSIGNAL_OPS_API_TOKEN_HASHES", "")))
        return values

    @staticmethod
    def _allow_unauthenticated_ops_api() -> bool:
        return OpsApiService._bool_env("OPENSIGNAL_OPS_API_ALLOW_UNAUTHENTICATED", False)

    @staticmethod
    def extract_api_token(api_token: str = "", authorization: str = "") -> str:
        raw_auth = authorization.strip()
        if raw_auth:
            lowered = raw_auth.lower()
            if lowered.startswith("bearer "):
                return raw_auth[7:].strip()
            return raw_auth
        return api_token.strip()

    @staticmethod
    def validate_access(api_token: str) -> tuple[bool, str]:
        if not OpsApiService.ops_api_enabled():
            return False, "Operational API is disabled by configuration."

        configured = OpsApiService.required_api_token_values()
        if not configured:
            if OpsApiService._allow_unauthenticated_ops_api():
                return True, "Operational API access granted (unauthenticated override enabled)."
            return False, "Operational API access denied: token configuration required."

        if not any_secret_matches(api_token, configured):
            return False, "Operational API access denied: invalid token."
        return True, "Operational API access granted."

    @staticmethod
    def _resolve_audit_export_path(file_path: str) -> str:
        base_dir = os.getenv("OPENSIGNAL_AUDIT_EXPORT_DIR", "runtime_reports").strip() or "runtime_reports"
        base_path = Path(base_dir).expanduser().resolve()

        configured_default = os.getenv("OPENSIGNAL_AUDIT_EXPORT_PATH", "latest_runtime_report.json")
        requested_raw = file_path.strip() or configured_default.strip() or "latest_runtime_report.json"
        requested_path = Path(requested_raw).expanduser()
        if requested_path.is_absolute():
            resolved_target = requested_path.resolve()
        else:
            resolved_target = (base_path / requested_path).resolve()

        try:
            resolved_target.relative_to(base_path)
        except ValueError as exc:
            raise ValueError(
                f"Audit export path must be within configured export directory: {base_path}"
            ) from exc
        return str(resolved_target)

    @staticmethod
    def _int_env(name: str, default: int) -> int:
        raw = os.getenv(name, str(default)).strip()
        try:
            return max(1, int(raw))
        except ValueError:
            return default

    @staticmethod
    def reset_warning_state() -> None:
        _warning_streaks.clear()

    @staticmethod
    def storage_warning_thresholds() -> dict[str, int]:
        return {
            "command_audit": OpsApiService._int_env("OPENSIGNAL_DB_WARN_COMMAND_AUDIT_ROWS", 50000),
            "status_snapshots": OpsApiService._int_env("OPENSIGNAL_DB_WARN_STATUS_SNAPSHOTS_ROWS", 200000),
            "alarm_acknowledgements": OpsApiService._int_env("OPENSIGNAL_DB_WARN_ALARM_ACK_ROWS", 5000),
            "alarm_silences": OpsApiService._int_env("OPENSIGNAL_DB_WARN_ALARM_SILENCES_ROWS", 5000),
            "alarm_events": OpsApiService._int_env("OPENSIGNAL_DB_WARN_ALARM_EVENTS_ROWS", 50000),
            "alert_webhook_queue": OpsApiService._int_env("OPENSIGNAL_DB_WARN_ALERT_WEBHOOK_QUEUE_ROWS", 2000),
            "alert_webhook_deadletter": OpsApiService._int_env("OPENSIGNAL_DB_WARN_ALERT_WEBHOOK_DEADLETTER_ROWS", 2000),
        }

    @staticmethod
    def _warning_severity(count: int, threshold: int) -> str:
        if count >= threshold * 2:
            return "critical"
        return "warn"

    @staticmethod
    def _warning_persistence_checks() -> int:
        return OpsApiService._int_env("OPENSIGNAL_DB_WARN_PERSISTENCE_CHECKS", 3)

    @staticmethod
    def storage_warning_details(counts: dict[str, int]) -> list[dict[str, Any]]:
        thresholds = OpsApiService.storage_warning_thresholds()
        details: list[dict[str, Any]] = []
        for table, threshold in thresholds.items():
            count = int(counts.get(table, 0))
            if count < threshold:
                continue
            details.append(
                {
                    "table": table,
                    "rows": count,
                    "threshold": threshold,
                    "severity": OpsApiService._warning_severity(count, threshold),
                }
            )
        return details

    @staticmethod
    def _update_warning_streaks(details: list[dict[str, Any]]) -> None:
        active_tables = {str(detail.get("table", "")) for detail in details}
        for table in list(_warning_streaks.keys()):
            if table not in active_tables:
                _warning_streaks[table] = 0

        for detail in details:
            table = str(detail.get("table", ""))
            if not table:
                continue
            _warning_streaks[table] = int(_warning_streaks.get(table, 0)) + 1

    @staticmethod
    def storage_persistent_alerts(details: list[dict[str, Any]]) -> list[str]:
        persist_checks = OpsApiService._warning_persistence_checks()
        alerts: list[str] = []
        for detail in details:
            table = str(detail.get("table", ""))
            streak = int(_warning_streaks.get(table, 0))
            if streak < persist_checks:
                continue
            severity = str(detail.get("severity", "warn"))
            rows = int(detail.get("rows", 0))
            threshold = int(detail.get("threshold", 0))
            alerts.append(
                (
                    f"storage alert: severity={severity} table={table} rows={rows} "
                    f"threshold={threshold} streak={streak}"
                )
            )
        return alerts

    @staticmethod
    def storage_growth_warnings(counts: dict[str, int]) -> list[str]:
        details = OpsApiService.storage_warning_details(counts)
        warnings: list[str] = []
        for detail in details:
            warnings.append(
                (
                    f"storage warning: severity={detail['severity']} "
                    f"table={detail['table']} rows={detail['rows']} "
                    f"threshold={detail['threshold']}"
                )
            )
        return warnings

    @staticmethod
    def health_snapshot() -> dict[str, Any]:
        counts = EventService.storage_table_counts()
        warning_details = OpsApiService.storage_warning_details(counts)
        OpsApiService._update_warning_streaks(warning_details)
        warnings = OpsApiService.storage_growth_warnings(counts)
        persistent_alerts = OpsApiService.storage_persistent_alerts(warning_details)
        dispatch = AlertDispatchService.dispatch_persistent_alerts(
            persistent_alerts,
            context={
                "table_row_counts": counts,
                "warning_details": warning_details,
            },
        )
        return {
            "generated_at": _utc_now_iso(),
            "runtime": PollingService.runtime_status(),
            "scheduler": scheduler_status(),
            "retention_cleanup": MaintenanceService.get_cleanup_status(),
            "storage": {
                "table_row_counts": counts,
                "warning_thresholds": OpsApiService.storage_warning_thresholds(),
                "warning_persistence_checks": OpsApiService._warning_persistence_checks(),
                "warning_details": warning_details,
                "warnings": warnings,
                "persistent_alerts": persistent_alerts,
                "alert_dispatch": dispatch,
            },
        }

    @staticmethod
    def alarms_snapshot(
        window_minutes: int | None = 60,
        command_limit: int = 200,
        snapshot_limit: int = 200,
    ) -> dict[str, Any]:
        payload = EventService.build_timeline_and_alarms(
            command_limit=command_limit,
            snapshot_limit=snapshot_limit,
            window_minutes=window_minutes,
        )
        return {
            "generated_at": _utc_now_iso(),
            "window_minutes": window_minutes,
            "active_count": len(payload.get("alarms", [])),
            "acknowledged_count": len(payload.get("acknowledged_alarms", [])),
            "silenced_count": len(payload.get("silenced_alarms", [])),
            "timeline_count": len(payload.get("timeline", [])),
            "payload": payload,
        }

    @staticmethod
    def alarm_history_snapshot(
        limit: int = 50,
        action_filter: str = "all",
        actor_contains: str = "",
        key_contains: str = "",
    ) -> dict[str, Any]:
        rows = EventService.list_alarm_history_rows(
            limit=limit,
            action_filter=action_filter,
            actor_contains=actor_contains,
            key_contains=key_contains,
        )
        return {
            "generated_at": _utc_now_iso(),
            "limit": limit,
            "action_filter": action_filter,
            "actor_contains": actor_contains,
            "key_contains": key_contains,
            "count": len(rows),
            "rows": rows,
        }

    @staticmethod
    def audit_export_snapshot(
        file_path: str = "",
        command_limit: int = 200,
        snapshot_limit: int = 200,
    ) -> dict[str, Any]:
        target = OpsApiService._resolve_audit_export_path(file_path)
        exported_path = STORE.export_activity_report(
            file_path=target,
            command_limit=max(1, min(1000, int(command_limit))),
            snapshot_limit=max(1, min(1000, int(snapshot_limit))),
            metadata={
                "source": "ops_api",
                "generated_at": _utc_now_iso(),
            },
        )
        return {
            "generated_at": _utc_now_iso(),
            "file_path": exported_path,
            "command_limit": max(1, min(1000, int(command_limit))),
            "snapshot_limit": max(1, min(1000, int(snapshot_limit))),
        }
