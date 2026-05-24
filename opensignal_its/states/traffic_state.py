import asyncio
import json
import os
from datetime import datetime
from typing import Any

import reflex as rx

from ..db import STORE
from ..models.fleet import FleetRefreshView
from ..services import (
    FleetService,
    PollingService,
)
from .auth_state import AuthStateMixin
from .command_state import CommandStateMixin
from .configuration_state import ConfigurationStateMixin
from .event_state import EventStateMixin
from .maintenance_state import MaintenanceStateMixin
from .monitor_state import MonitorStateMixin
from .polling_state import PollingStateMixin
from .safety_state import SafetyStateMixin



def _fleet_view_to_state_fields(refresh_view: FleetRefreshView) -> dict[str, Any]:
    return {
        "selected_device_id": str(refresh_view.selected_device_id),
        "fleet_status_by_id": {
            key: value.model_dump(mode="json")
            for key, value in refresh_view.status_by_id.items()
        },
        "fleet_device_rows": list(refresh_view.rows),
        "selected_payload": refresh_view.selected_payload,
        "selected_mp_model": int(refresh_view.selected_mp_model),
        "selected_device_type": str(refresh_view.selected_device_type),
    }


class TrafficState(CommandStateMixin, MonitorStateMixin, ConfigurationStateMixin, SafetyStateMixin, AuthStateMixin, MaintenanceStateMixin, PollingStateMixin, EventStateMixin, rx.State):
    """Main app state."""

    error: str = ""
    is_loading: bool = False
    fleet_status_summary: str = "Controller view idle."
    fleet_device_rows: list[str] = []
    fleet_status_by_id: dict[str, dict[str, Any]] = {}
    fleet_online_count: int = 0
    fleet_offline_count: int = 0
    fleet_total_count: int = 0
    audit_export_notice: str = ""
    audit_export_path: str = ""
    auto_refresh_enabled: bool = True
    refresh_interval_text: str = "5"
    auto_reconnect_enabled: bool = True
    reconnect_interval_text: str = "10"
    auto_refresh_running: bool = False
    ui_workspace_mode: str = "monitor"

    def update_auto_refresh_enabled(self, value: bool):
        self.auto_refresh_enabled = value

    def update_refresh_interval_text(self, value: str):
        self.refresh_interval_text = value

    def update_auto_reconnect_enabled(self, value: bool):
        self.auto_reconnect_enabled = value

    def update_reconnect_interval_text(self, value: str):
        self.reconnect_interval_text = value

    def update_ui_workspace_mode(self, value: str):
        normalized = value.strip().lower()
        if normalized in {"monitor", "control", "operations", "analytics", "configuration", "admin"}:
            self.ui_workspace_mode = normalized
            if normalized == "configuration":
                self._sync_controller_profile_rows()

    def _refresh_interval_seconds(self) -> float:
        try:
            return max(1.0, float(self.refresh_interval_text))
        except ValueError:
            return 5.0

    def _reconnect_interval_seconds(self) -> float:
        try:
            return max(2.0, float(self.reconnect_interval_text))
        except ValueError:
            return 10.0

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.utcnow().isoformat()

    def _has_expired(self, ts: str) -> bool:
        parsed = self._parse_timestamp(ts)
        now = datetime.utcnow()
        if parsed is None:
            return True
        # _parse_timestamp may return timezone-aware dt if offset is included.
        if parsed.tzinfo is not None:
            return now.replace(tzinfo=parsed.tzinfo) >= parsed
        return now >= parsed

    def _fleet_profiles(self) -> list[dict[str, Any]]:
        return FleetService.parse_profiles_json(self.device_profiles_json)

    def _refresh_fleet_aggregate_fields(self):
        summary = FleetService.summarize_status_map(self.fleet_status_by_id)
        self.fleet_total_count = int(summary["total"])
        self.fleet_online_count = int(summary["online"])
        self.fleet_offline_count = int(summary["offline"])
        if self.fleet_total_count > 0:
            self.fleet_status_summary = (
                f"Controllers: {self.fleet_total_count} total, "
                f"{self.fleet_online_count} online, {self.fleet_offline_count} offline."
            )

    def _cache_device_status(self, device_id: str, device_type: str, payload: dict[str, Any]):
        cache = dict(self.fleet_status_by_id)
        cache[device_id] = {
            "device_type": device_type,
            "is_online": bool(payload.get("is_online", False)),
            "status_text": str(payload.get("status_text", "unknown")),
            "timestamp": str(payload.get("timestamp", "")),
        }
        self.fleet_status_by_id = cache

        rows = list(self.fleet_device_rows)
        row = FleetService.format_status_row(device_id, device_type, payload)
        replaced = False
        for i, existing in enumerate(rows):
            if existing.startswith(f"{device_id} [{device_type}]"):
                rows[i] = row
                replaced = True
                break
        if not replaced:
            rows.append(row)
        self.fleet_device_rows = rows
        self._refresh_fleet_aggregate_fields()
        self._sync_controller_profile_rows()

    def export_audit_report(self):
        if not self._is_role_authorized({"admin"}):
            self.audit_export_notice = "Audit export denied: admin authentication required."
            self.error = self.audit_export_notice
            return

        target_path = os.getenv("OPENSIGNAL_AUDIT_EXPORT_PATH", "runtime_reports/latest_runtime_report.json")
        metadata = {
            "operator": self.current_operator,
            "role": self.current_role,
            "runtime_health": self.runtime_health_notice,
            "scheduler_enabled": self.retention_scheduler_enabled,
            "scheduler_running": self.retention_scheduler_running,
            "scheduler_interval_seconds": self.retention_scheduler_interval_text,
        }
        try:
            exported_path = STORE.export_activity_report(
                file_path=target_path,
                command_limit=200,
                snapshot_limit=200,
                metadata=metadata,
            )
            self.audit_export_path = exported_path
            self.audit_export_notice = f"Audit report exported to {exported_path}."
            self.error = ""
        except Exception as exc:
            self.audit_export_notice = f"Audit report export failed: {exc}"
            self.error = self.audit_export_notice

    async def refresh_fleet_status(self):
        try:
            profiles = self._fleet_profiles()
        except Exception as exc:
            self.fleet_status_summary = f"Controller profile parse failed: {exc}"
            self.fleet_device_rows = []
            self.error = self.fleet_status_summary
            return

        if not profiles:
            self.fleet_status_summary = "Controller profile list is empty; using single-controller compatibility mode."
            self.fleet_device_rows = []
            self._sync_controller_profile_rows()
            return

        refresh_view = await FleetService.collect_refresh_view(
            profiles=profiles,
            selected_device_id=self.selected_device_id,
            collector=PollingService.collect_snapshot,
        )
        adapted = _fleet_view_to_state_fields(refresh_view)
        self.selected_device_id = str(adapted["selected_device_id"])
        self.fleet_status_by_id = dict(adapted["fleet_status_by_id"])
        self.fleet_device_rows = list(adapted["fleet_device_rows"])
        self._sync_controller_profile_rows()
        self._refresh_fleet_aggregate_fields()
        self.refresh_runtime_registry_status()

        selected_payload = adapted["selected_payload"]
        if selected_payload is not None:
            self._apply_status_snapshot(
                dict(selected_payload),
                int(adapted["selected_mp_model"]),
            )
            self._cache_device_status(
                self.selected_device_id,
                str(adapted["selected_device_type"]),
                dict(selected_payload),
            )

    @rx.event(background=True)
    async def auto_refresh_loop(self):
        """Continuously poll while online and auto-reconnect when offline."""
        async with self:
            if self.auto_refresh_running:
                return
            self.auto_refresh_running = True

        try:
            while True:
                async with self:
                    refresh_enabled = self.auto_refresh_enabled
                    reconnect_enabled = self.auto_reconnect_enabled
                    is_online = self.is_online
                    is_loading = self.is_loading
                    refresh_interval = self._refresh_interval_seconds()
                    reconnect_interval = self._reconnect_interval_seconds()

                    should_continue = refresh_enabled or reconnect_enabled
                if not should_continue:
                    break

                if is_loading:
                    await asyncio.sleep(1.0)
                    await asyncio.sleep(refresh_interval)
                    continue

                if (not is_online) and reconnect_enabled:
                    try:
                        device_id, device_type, status_payload, mp_model = await self._collect_selected_status_snapshot()
                    except ValueError:
                        async with self:
                            self.m60_status = {
                                "error": "Port, timeout, and retries must be numeric.",
                            }
                            self.m60_status_json = json.dumps(self.m60_status, indent=2)
                            self.error = self.m60_status["error"]
                            self.status_text = "Input validation failed"
                            self.is_online = False
                    except Exception as e:
                        async with self:
                            self.m60_status = {"error": f"Unhandled exception: {e}"}
                            self.m60_status_json = json.dumps(self.m60_status, indent=2)
                            self.error = self.m60_status["error"]
                            self.status_text = "Unhandled exception"
                            self.is_online = False
                    else:
                        async with self:
                            self._apply_status_snapshot(status_payload, mp_model)
                            self._cache_device_status(device_id, device_type, status_payload)
                    await asyncio.sleep(reconnect_interval)
                    continue

                await asyncio.sleep(1.0)
        finally:
            async with self:
                self.auto_refresh_running = False
