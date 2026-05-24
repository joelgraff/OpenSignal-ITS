import asyncio
import json
import os
import random
from datetime import datetime
from typing import Any
from uuid import uuid4

import reflex as rx

from ..devices.parsers import build_siemens_m60_view
from ..db import CommandAuditRecord, STORE
from ..models.device import DeviceConfig
from ..models.fleet import FleetRefreshView
from ..services import (
    CommandSafetyService,
    CommandService,
    FleetService,
    PollingService,
)
from .auth_state import AuthStateMixin
from .event_state import EventStateMixin
from .maintenance_state import MaintenanceStateMixin
from .polling_state import PollingStateMixin



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


class TrafficState(AuthStateMixin, MaintenanceStateMixin, PollingStateMixin, EventStateMixin, rx.State):
    """Main app state."""

    m60_status: dict = {}
    m60_status_json: str = ""
    status_text: str = "No status yet"
    active_snmp_version: str = "unknown"
    current_pattern: str = "Unknown"
    unit_status: str = "unknown"
    green_phases: str = "none"
    yellow_phases: str = "none"
    red_phases: str = "none"
    vehicle_calls: str = "none"
    ped_calls: str = "none"
    remaining_time_summary: str = "none"
    timer_mode_text: str = "unknown"
    ring_status_summary: str = "unknown"
    ring_status_lines: list[str] = []
    ring_status_console_text: str = "RING STATUS CONSOLE\n(no data)"
    last_ring_status_raw: dict[str, int] = {}
    ring_state_age_seconds: dict[str, int] = {}
    phase_data: dict[str, dict[str, bool | int]] = {}
    phase_current_pattern: str = "Unknown"
    phase_unit_control_status: str = "unknown"
    phase_detail_lines: list[str] = []
    last_timer_snapshot: dict[str, int] = {}
    phase_state_age_seconds: dict[str, int] = {}
    last_phase_state_signature: dict[str, str] = {}
    is_online: bool = False
    last_updated: str = ""
    error: str = ""
    is_loading: bool = False
    ip_address: str = "166.156.88.223"
    port_text: str = "161"
    community: str = "public"
    snmp_version: str = "auto"
    timeout_text: str = "3"
    retries_text: str = "1"
    device_profiles_json: str = "[]"
    controller_profile_rows: list[dict[str, Any]] = []
    controller_profile_notice: str = "No controller profiles configured yet."
    controller_profile_filter_text: str = ""
    controller_profile_sort_key: str = "device_id"
    controller_profile_sort_desc: bool = False
    controller_profile_form_error: str = ""
    controller_profile_original_device_id: str = ""
    controller_profile_form_device_id: str = ""
    controller_profile_form_name: str = ""
    controller_profile_form_device_type: str = FleetService.DEFAULT_DEVICE_TYPE
    controller_profile_form_ip_address: str = ""
    controller_profile_form_port_text: str = "161"
    controller_profile_form_community: str = "public"
    controller_profile_form_snmp_version: str = "auto"
    controller_profile_form_timeout_text: str = "3"
    controller_profile_form_retries_text: str = "1"
    selected_device_id: str = ""
    fleet_status_summary: str = "Controller view idle."
    fleet_device_rows: list[str] = []
    fleet_status_by_id: dict[str, dict[str, Any]] = {}
    fleet_online_count: int = 0
    fleet_offline_count: int = 0
    fleet_total_count: int = 0
    safe_command_probe: bool = True
    operator_key_input: str = ""
    write_unlock_seconds_text: str = "120"
    write_unlock_until: str = ""
    write_mode_active: bool = False
    safety_notice: str = "Write mode locked."
    confirmation_input: str = ""
    pending_confirmation_token: str = ""
    pending_confirmation_expires: str = ""
    pending_command_type: str = ""
    pending_command_value_json: str = ""
    pending_confirmation_notice: str = ""
    audit_export_notice: str = ""
    audit_export_path: str = ""
    auto_refresh_enabled: bool = True
    refresh_interval_text: str = "5"
    auto_reconnect_enabled: bool = True
    reconnect_interval_text: str = "10"
    auto_refresh_running: bool = False
    ui_workspace_mode: str = "monitor"
    monitor_detail_tab: str = "logs"
    monitor_view: str = "dashboard"

    def update_ip_address(self, value: str):
        self.ip_address = value

    def update_port_text(self, value: str):
        self.port_text = value

    def update_community(self, value: str):
        self.community = value

    def update_snmp_version(self, value: str):
        self.snmp_version = value

    def update_device_profiles_json(self, value: str):
        self.device_profiles_json = value
        self.controller_profile_form_error = ""
        self._sync_controller_profile_rows()

    def update_selected_device_id(self, value: str):
        self.selected_device_id = value

    def update_controller_profile_filter_text(self, value: str):
        self.controller_profile_filter_text = value
        self._sync_controller_profile_rows()

    def update_controller_profile_sort_key(self, value: str):
        normalized = value.strip().lower()
        if normalized not in {"device_id", "name", "ip_address"}:
            return
        if self.controller_profile_sort_key == normalized:
            self.controller_profile_sort_desc = not self.controller_profile_sort_desc
        else:
            self.controller_profile_sort_key = normalized
            self.controller_profile_sort_desc = False
        self._sync_controller_profile_rows()

    def toggle_controller_profile_sort_direction(self):
        self.controller_profile_sort_desc = not self.controller_profile_sort_desc
        self._sync_controller_profile_rows()

    def update_controller_profile_form_device_id(self, value: str):
        self.controller_profile_form_device_id = value

    def update_controller_profile_form_name(self, value: str):
        self.controller_profile_form_name = value

    def update_controller_profile_form_device_type(self, value: str):
        self.controller_profile_form_device_type = value

    def update_controller_profile_form_ip_address(self, value: str):
        self.controller_profile_form_ip_address = value

    def update_controller_profile_form_port_text(self, value: str):
        self.controller_profile_form_port_text = value

    def update_controller_profile_form_community(self, value: str):
        self.controller_profile_form_community = value

    def update_controller_profile_form_snmp_version(self, value: str):
        self.controller_profile_form_snmp_version = value

    def update_controller_profile_form_timeout_text(self, value: str):
        self.controller_profile_form_timeout_text = value

    def update_controller_profile_form_retries_text(self, value: str):
        self.controller_profile_form_retries_text = value

    def update_timeout_text(self, value: str):
        self.timeout_text = value

    def update_retries_text(self, value: str):
        self.retries_text = value

    def update_safe_command_probe(self, value: bool):
        self.safe_command_probe = value
        if value:
            self.write_mode_active = False
            self.write_unlock_until = ""
            self.safety_notice = "Probe mode enabled. Write mode locked."

    def update_operator_key_input(self, value: str):
        self.operator_key_input = value

    def update_write_unlock_seconds_text(self, value: str):
        self.write_unlock_seconds_text = value

    def update_confirmation_input(self, value: str):
        self.confirmation_input = value

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

    def update_monitor_detail_tab(self, value: str):
        normalized = value.strip().lower()
        if normalized in {"logs", "timing", "video", "raw", "cabinet"}:
            self.monitor_detail_tab = normalized

    def update_monitor_view(self, value: str):
        normalized = value.strip().lower()
        if normalized in {"dashboard", "intersection"}:
            self.monitor_view = normalized

    def open_intersection_detail(self):
        self.monitor_view = "intersection"

    def back_to_dashboard(self):
        self.monitor_view = "dashboard"

    def select_controller_from_row(self, row: str):
        tokenized = row.strip().split()
        if tokenized:
            self.selected_device_id = tokenized[0]
            self.monitor_view = "intersection"

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

    def _write_unlock_seconds(self) -> int:
        try:
            return max(15, int(self.write_unlock_seconds_text))
        except ValueError:
            return 120

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

    def _requires_confirmation(self, cmd_type: str) -> bool:
        if self.safe_command_probe:
            return False
        return cmd_type in {
            "select_pattern",
            "set_mode",
            "manual_hold",
            "advance_phase",
        }

    def _start_command_confirmation(self, cmd_type: str, value: Any):
        token = str(random.randint(100000, 999999))
        expires = datetime.utcnow().timestamp() + 90
        self.pending_confirmation_token = token
        self.pending_confirmation_expires = datetime.utcfromtimestamp(expires).isoformat()
        self.pending_command_type = cmd_type
        self.pending_command_value_json = json.dumps(value)
        self.pending_confirmation_notice = (
            f"Confirmation required for {cmd_type}. Enter token {token} within 90 seconds."
        )

    def _build_config(self) -> DeviceConfig:
        port = int(self.port_text)
        timeout_seconds = float(self.timeout_text)
        retries = int(self.retries_text)
        return DeviceConfig(
            ip_address=self.ip_address.strip(),
            port=port,
            name="Siemens M60 Test",
            community=self.community.strip(),
            snmp_version=self.snmp_version.strip().lower(),
            timeout_seconds=timeout_seconds,
            retries=retries,
        )

    def _reset_controller_profile_form(self):
        self.controller_profile_form_error = ""
        self.controller_profile_original_device_id = ""
        self.controller_profile_form_device_id = ""
        self.controller_profile_form_name = ""
        self.controller_profile_form_device_type = FleetService.DEFAULT_DEVICE_TYPE
        self.controller_profile_form_ip_address = ""
        self.controller_profile_form_port_text = "161"
        self.controller_profile_form_community = "public"
        self.controller_profile_form_snmp_version = "auto"
        self.controller_profile_form_timeout_text = "3"
        self.controller_profile_form_retries_text = "1"

    def _sync_controller_profile_rows(self, notice: str = "") -> list[dict[str, Any]]:
        try:
            profiles = FleetService.parse_profiles_json(self.device_profiles_json)
        except Exception as exc:
            self.controller_profile_rows = []
            self.controller_profile_notice = f"Profile JSON error: {exc}"
            return []

        filtered_profiles = FleetService.filter_profiles(profiles, self.controller_profile_filter_text)
        ordered_profiles = FleetService.sort_profiles(
            filtered_profiles,
            self.controller_profile_sort_key,
            self.controller_profile_sort_desc,
        )
        self.controller_profile_rows = FleetService.build_profile_display_rows(
            ordered_profiles,
            self.fleet_status_by_id,
        )
        summary_suffix = ""
        query = self.controller_profile_filter_text.strip()
        if query and profiles:
            summary_suffix = f" Showing {len(filtered_profiles)} of {len(profiles)} controller profiles."

        if notice:
            self.controller_profile_notice = notice + summary_suffix
        elif not profiles:
            self.controller_profile_notice = "No controller profiles configured yet."
        elif query and not filtered_profiles:
            self.controller_profile_notice = f'No controller profiles match "{query}".'
        else:
            suffix = "" if len(profiles) == 1 else "s"
            self.controller_profile_notice = f"{len(profiles)} controller profile{suffix} configured.{summary_suffix}"
        return profiles

    def new_controller_profile(self):
        self._reset_controller_profile_form()
        self._sync_controller_profile_rows("Ready to add a controller profile.")

    def load_controller_profile(self, device_id: str):
        profiles = self._sync_controller_profile_rows()
        target = device_id.strip()
        if not target:
            self.controller_profile_notice = "Choose a controller profile to load."
            return

        selected = next(
            (
                profile
                for profile in profiles
                if str(profile.get("device_id", "")).strip() == target
            ),
            None,
        )
        if selected is None:
            self.controller_profile_notice = f"Controller profile {target} was not found."
            return

        self.controller_profile_original_device_id = str(selected.get("device_id", "")).strip()
        self.controller_profile_form_device_id = str(selected.get("device_id", "")).strip()
        self.controller_profile_form_name = str(selected.get("name", "")).strip()
        self.controller_profile_form_device_type = str(
            selected.get("device_type", FleetService.DEFAULT_DEVICE_TYPE)
        ).strip() or FleetService.DEFAULT_DEVICE_TYPE
        self.controller_profile_form_ip_address = str(selected.get("ip_address", "")).strip()
        self.controller_profile_form_port_text = str(selected.get("port", 161)).strip()
        self.controller_profile_form_community = str(selected.get("community", "public")).strip()
        self.controller_profile_form_snmp_version = str(selected.get("snmp_version", "auto")).strip()
        self.controller_profile_form_timeout_text = str(selected.get("timeout_seconds", 3.0)).strip()
        self.controller_profile_form_retries_text = str(selected.get("retries", 1)).strip()
        self.selected_device_id = self.controller_profile_form_device_id
        self.controller_profile_notice = f"Loaded controller profile {target}."
        self.controller_profile_form_error = ""

    def load_controller_profile_from_row(self, device_id: str):
        self.load_controller_profile(device_id)

    def save_controller_profile(self):
        self.controller_profile_form_error = ""
        try:
            profiles = FleetService.parse_profiles_json(self.device_profiles_json)
        except Exception as exc:
            self.controller_profile_notice = f"Cannot save until Advanced JSON is valid: {exc}"
            return

        target_device_id = self.controller_profile_form_device_id.strip()
        try:
            updated_profiles = list(profiles)
            original_device_id = self.controller_profile_original_device_id.strip()
            if original_device_id and original_device_id != target_device_id:
                updated_profiles = FleetService.remove_profile(updated_profiles, original_device_id)
            profile = FleetService.build_profile_from_form(
                device_id=target_device_id,
                name=self.controller_profile_form_name,
                device_type=self.controller_profile_form_device_type,
                ip_address_text=self.controller_profile_form_ip_address,
                port_text=self.controller_profile_form_port_text,
                community=self.controller_profile_form_community,
                snmp_version=self.controller_profile_form_snmp_version,
                timeout_text=self.controller_profile_form_timeout_text,
                retries_text=self.controller_profile_form_retries_text,
            )
            updated_profiles = FleetService.upsert_profile(updated_profiles, profile)
        except Exception as exc:
            self.controller_profile_form_error = str(exc)
            self.controller_profile_notice = f"Cannot save controller profile: {exc}"
            return

        self.device_profiles_json = FleetService.dump_profiles_json(updated_profiles)
        self.controller_profile_original_device_id = target_device_id
        if target_device_id:
            self.selected_device_id = target_device_id
        self.controller_profile_form_error = ""
        self._sync_controller_profile_rows(f"Saved controller profile {target_device_id}.")

    def delete_controller_profile(self):
        target = self.controller_profile_original_device_id.strip() or self.controller_profile_form_device_id.strip()
        if not target:
            self.controller_profile_notice = "Choose a controller profile to delete."
            return

        try:
            profiles = FleetService.parse_profiles_json(self.device_profiles_json)
        except Exception as exc:
            self.controller_profile_notice = f"Cannot delete until Advanced JSON is valid: {exc}"
            return

        updated_profiles = FleetService.remove_profile(profiles, target)
        if len(updated_profiles) == len(profiles):
            self.controller_profile_notice = f"Controller profile {target} was not found."
            return

        self.device_profiles_json = FleetService.dump_profiles_json(updated_profiles)
        if self.selected_device_id.strip() == target:
            self.selected_device_id = ""
        self._reset_controller_profile_form()
        self._sync_controller_profile_rows(f"Removed controller profile {target}.")

    def open_selected_controller_status(self):
        target = self.controller_profile_form_device_id.strip() or self.controller_profile_original_device_id.strip()
        if not target:
            self.controller_profile_notice = "Save or load a controller profile before opening Controller Status."
            return

        self.selected_device_id = target
        self.ui_workspace_mode = "monitor"
        self.monitor_view = "intersection"
        self.controller_profile_notice = f"Opened Controller Status for {target}."

    def _fleet_profiles(self) -> list[dict[str, Any]]:
        return FleetService.parse_profiles_json(self.device_profiles_json)

    def _selected_device_target(self) -> tuple[str, str, DeviceConfig]:
        profiles = self._fleet_profiles()
        return FleetService.resolve_target(
            profiles=profiles,
            selected_device_id=self.selected_device_id,
            fallback_config=self._build_config(),
            fallback_device_id=self.ip_address.strip() or "single-device",
            fallback_device_type=FleetService.DEFAULT_DEVICE_TYPE,
        )

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

    def _parse_timestamp(self, ts: str) -> datetime | None:
        if not ts:
            return None
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _poll_delta_seconds(self, previous_ts: str, current_ts: str) -> int:
        prev = self._parse_timestamp(previous_ts)
        curr = self._parse_timestamp(current_ts)
        if prev is None or curr is None:
            return 0
        delta = int((curr - prev).total_seconds())
        return max(0, delta)

    def _apply_phase_payload(self, payload: dict, poll_delta_seconds: int = 0):
        parsed = build_siemens_m60_view(
            payload=payload,
            poll_delta_seconds=poll_delta_seconds,
            previous_phase_state_age=self.phase_state_age_seconds,
            previous_phase_signatures=self.last_phase_state_signature,
            previous_ring_raw=self.last_ring_status_raw,
            previous_ring_age=self.ring_state_age_seconds,
            previous_timer_snapshot=self.last_timer_snapshot,
        )

        self.current_pattern = str(parsed["current_pattern"])
        self.unit_status = str(parsed["unit_status"])
        self.green_phases = str(parsed["green_phases"])
        self.yellow_phases = str(parsed["yellow_phases"])
        self.red_phases = str(parsed["red_phases"])
        self.vehicle_calls = str(parsed["vehicle_calls"])
        self.ped_calls = str(parsed["ped_calls"])
        self.phase_data = dict(parsed["phase_data"])
        self.phase_current_pattern = str(parsed["phase_current_pattern"])
        self.phase_unit_control_status = str(parsed["phase_unit_control_status"])
        self.phase_detail_lines = list(parsed["phase_detail_lines"])
        self.phase_state_age_seconds = dict(parsed["phase_state_age_seconds"])
        self.last_phase_state_signature = dict(parsed["last_phase_state_signature"])
        self.remaining_time_summary = str(parsed["remaining_time_summary"])
        self.timer_mode_text = str(parsed["timer_mode_text"])
        self.last_timer_snapshot = dict(parsed["last_timer_snapshot"])
        self.last_ring_status_raw = dict(parsed["last_ring_status_raw"])
        self.ring_state_age_seconds = dict(parsed["ring_state_age_seconds"])
        self.ring_status_summary = str(parsed["ring_status_summary"])
        self.ring_status_lines = list(parsed["ring_status_lines"])
        self.ring_status_console_text = str(parsed["ring_status_console_text"])

    async def _collect_status_snapshot(self) -> tuple[dict, int]:
        """Fetch one controller status snapshot without mutating UI state."""
        device_type, device_id, config = self._selected_device_target()
        return await PollingService.collect_snapshot(device_type, config, device_id=device_id)

    async def _collect_selected_status_snapshot(self) -> tuple[str, str, dict, int]:
        device_type, device_id, config = self._selected_device_target()
        payload, mp_model = await PollingService.collect_snapshot(device_type, config, device_id=device_id)
        return device_id, device_type, payload, mp_model

    def _apply_status_snapshot(self, status_payload: dict, mp_model: int):
        """Apply one status snapshot to state fields used by the UI."""
        previous_updated = self.last_updated
        self.m60_status = status_payload
        self.m60_status_json = json.dumps(self.m60_status, indent=2)
        self.status_text = str(self.m60_status.get("status_text", "Unknown"))
        self.is_online = bool(self.m60_status.get("is_online", False))
        self.last_updated = str(self.m60_status.get("timestamp", ""))
        poll_delta_seconds = self._poll_delta_seconds(previous_updated, self.last_updated)
        self._apply_phase_payload(self.m60_status, poll_delta_seconds)
        self.active_snmp_version = "v2c" if mp_model == 1 else "v1"
        errors = self.m60_status.get("errors", [])
        self.error = "; ".join(errors) if errors else ""
        self._safe_log_status_snapshot(status_payload)

    def _safe_log_status_snapshot(
        self,
        payload: dict,
        correlation_id: str = "",
        source: str = "poll",
    ):
        try:
            STORE.log_status_snapshot(
                device_ip=self.ip_address.strip(),
                payload=payload,
                correlation_id=correlation_id,
                source=source,
            )
        except Exception:
            # Logging should not block polling/control flows.
            pass

    def _safe_log_command(
        self,
        cmd_type: str,
        value: Any,
        correlation_id: str,
        allowed: bool,
        success: bool,
        error: str,
    ):
        try:
            STORE.log_command(
                CommandAuditRecord(
                    timestamp=datetime.utcnow().isoformat(),
                    correlation_id=correlation_id,
                    device_ip=self.ip_address.strip(),
                    command_type=cmd_type,
                    command_value=value,
                    probe_only=self.safe_command_probe,
                    allowed=allowed,
                    success=success,
                    error=error,
                    actor=self._actor_name(),
                )
            )
        except Exception:
            # Logging should not block command execution paths.
            pass

    def unlock_write_mode(self):
        if not self._is_role_authorized({"operator", "admin"}):
            self.safety_notice = "Write unlock denied: operator or admin authentication required."
            self.error = self.safety_notice
            return

        success, message, unlock_until = CommandSafetyService.unlock_write_mode(
            operator_key_input=self.operator_key_input,
            requested_seconds=self._write_unlock_seconds(),
        )
        if success:
            self.safe_command_probe = False
            self.write_mode_active = True
            self.write_unlock_until = unlock_until
        else:
            self.safe_command_probe = True
            self.write_mode_active = False
            self.write_unlock_until = ""
        self.safety_notice = message
        self.error = "" if success else message

    def lock_write_mode(self):
        self.safe_command_probe = True
        self.write_mode_active = False
        self.write_unlock_until = ""
        self.safety_notice = "Write mode locked."

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

    async def confirm_pending_command(self):
        if not self.pending_command_type:
            self.error = "No pending command to confirm."
            return
        if self._has_expired(self.pending_confirmation_expires):
            self.error = "Confirmation token expired."
            self.pending_confirmation_token = ""
            self.pending_confirmation_expires = ""
            self.pending_command_type = ""
            self.pending_command_value_json = ""
            self.pending_confirmation_notice = ""
            return
        if self.confirmation_input.strip() != self.pending_confirmation_token:
            self.error = "Confirmation token mismatch."
            return

        cmd_type = self.pending_command_type
        value: Any = None
        if self.pending_command_value_json:
            value = json.loads(self.pending_command_value_json)

        self.pending_confirmation_token = ""
        self.pending_confirmation_expires = ""
        self.pending_command_type = ""
        self.pending_command_value_json = ""
        self.pending_confirmation_notice = ""
        self.confirmation_input = ""

        await self.send_command(cmd_type, value, force_confirmed=True)

    async def connect_m60(self):
        await self.add_and_poll_m60()
        if (self.auto_refresh_enabled or self.auto_reconnect_enabled) and not self.auto_refresh_running:
            return TrafficState.auto_refresh_loop

    async def refresh_status(self):
        await self.add_and_poll_m60()

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
                    continue

                if is_online and refresh_enabled:
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

    async def add_and_poll_m60(self):
        self.is_loading = True
        try:
            try:
                device_id, device_type, status_payload, mp_model = await self._collect_selected_status_snapshot()
            except ValueError:
                self.m60_status = {
                    "error": "Port, timeout, and retries must be numeric.",
                }
                self.m60_status_json = json.dumps(self.m60_status, indent=2)
                self.error = self.m60_status["error"]
                self.status_text = "Input validation failed"
                self.is_online = False
                return
            self._apply_status_snapshot(status_payload, mp_model)
            self._cache_device_status(device_id, device_type, status_payload)
        except Exception as e:
            self.m60_status = {"error": f"Unhandled exception: {e}"}
            self.m60_status_json = json.dumps(self.m60_status, indent=2)
            self.error = self.m60_status["error"]
            self.status_text = "Unhandled exception"
            self.is_online = False
        finally:
            self.is_loading = False

    async def send_command(self, cmd_type: str, value: Any, force_confirmed: bool = False):
        """Send timing-related commands to the controller."""
        self.is_loading = True
        correlation_id = uuid4().hex
        try:
            if not self._is_role_authorized({"operator", "admin"}):
                auth_error = "Command denied: operator or admin authentication required."
                self.error = auth_error
                self._safe_log_command(
                    cmd_type=cmd_type,
                    value=value,
                    correlation_id=correlation_id,
                    allowed=False,
                    success=False,
                    error=auth_error,
                )
                return

            if self._requires_confirmation(cmd_type) and not force_confirmed:
                self._start_command_confirmation(cmd_type, value)
                self.error = self.pending_confirmation_notice
                self._safe_log_command(
                    cmd_type=cmd_type,
                    value=value,
                    correlation_id=correlation_id,
                    allowed=False,
                    success=False,
                    error="Confirmation required before write command execution.",
                )
                return

            safety = CommandSafetyService.evaluate_command(
                safe_command_probe=self.safe_command_probe,
                write_unlock_until=self.write_unlock_until,
            )
            self.safety_notice = safety.reason
            if not safety.allowed:
                self.safe_command_probe = True
                self.write_mode_active = False
                self.write_unlock_until = ""
                self.error = safety.reason
                self._safe_log_command(
                    cmd_type=cmd_type,
                    value=value,
                    correlation_id=correlation_id,
                    allowed=False,
                    success=False,
                    error=safety.reason,
                )
                return

            device_type, device_id, config = self._selected_device_target()
            success, payload, mp_model, error = await CommandService.execute_command(
                device_type=device_type,
                config=config,
                cmd_type=cmd_type,
                value=value,
                safe_command_probe=self.safe_command_probe,
                device_id=device_id,
            )
            self._safe_log_command(
                cmd_type=cmd_type,
                value=value,
                correlation_id=correlation_id,
                allowed=True,
                success=success,
                error=error,
            )
            if success:
                self.m60_status = payload
                self.m60_status_json = json.dumps(self.m60_status, indent=2)
                self.status_text = str(self.m60_status.get("status_text", "Command applied"))
                self.is_online = bool(self.m60_status.get("is_online", False))
                self.last_updated = str(self.m60_status.get("timestamp", ""))
                self._apply_phase_payload(self.m60_status)
                self.active_snmp_version = "v2c" if mp_model == 1 else "v1"
                errors = self.m60_status.get("errors", [])
                self.error = "; ".join(errors) if errors else ""
                self._safe_log_status_snapshot(
                    self.m60_status,
                    correlation_id=correlation_id,
                    source="command",
                )
                self._cache_device_status(device_id, device_type, self.m60_status)
            else:
                self.m60_status = payload
                self.m60_status_json = json.dumps(self.m60_status, indent=2)
                self.error = error
                self.is_online = bool(self.m60_status.get("is_online", False))
                self._cache_device_status(device_id, device_type, self.m60_status)
        except Exception as e:
            self.error = str(e)
        finally:
            self.is_loading = False

    async def connect_and_start_polling(self):
        self.refresh_runtime_health()
        self.refresh_runtime_registry_status()
        return await self.connect_m60()

    async def select_pattern_1(self):
        await self.send_command("select_pattern", 1)

    async def select_pattern_2(self):
        await self.send_command("select_pattern", 2)

    async def set_mode_free(self):
        await self.send_command("set_mode", "free")

    async def set_mode_coordinated(self):
        await self.send_command("set_mode", "coordinated")

    async def manual_hold(self):
        await self.send_command("manual_hold", True)

    async def advance_phase(self):
        await self.send_command("advance_phase", True)