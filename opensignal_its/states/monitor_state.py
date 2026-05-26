"""Single-controller monitor and snapshot state slice."""

from __future__ import annotations

import json
from typing import Any

import reflex as rx

from ..devices.parsers import build_siemens_m60_view
from ..db import STORE
from ..models.device import DeviceConfig
from ..services import FleetService, PollingService


class MonitorStateMixin(rx.State, mixin=True):
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
    ip_address: str = "166.156.88.223"
    port_text: str = "161"
    community: str = "public"
    snmp_version: str = "auto"
    timeout_text: str = "3"
    retries_text: str = "1"
    selected_device_id: str = ""
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

    def update_selected_device_id(self, value: str):
        self.selected_device_id = value
        refresh_map = getattr(self, "_refresh_fleet_map_fields", None)
        if callable(refresh_map):
            refresh_map()

    def update_timeout_text(self, value: str):
        self.timeout_text = value

    def update_retries_text(self, value: str):
        self.retries_text = value

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
            close_dialog = getattr(self, "close_controller_profile_creation_dialog", None)
            if callable(close_dialog):
                close_dialog()
            refresh_map = getattr(self, "_refresh_fleet_map_fields", None)
            if callable(refresh_map):
                refresh_map()

    def select_controller_from_map_points(self, points: list[dict[str, Any]]):
        if not points:
            return

        first = dict(points[0])
        try:
            point_number = int(first.get("pointNumber", -1))
        except (TypeError, ValueError):
            return

        if point_number < 0 or point_number >= len(self.fleet_map_markers):
            return

        marker = dict(self.fleet_map_markers[point_number])
        device_id = str(marker.get("device_id", "")).strip()
        if not device_id:
            return

        self.selected_device_id = device_id
        self.monitor_view = "intersection"
        close_dialog = getattr(self, "close_controller_profile_creation_dialog", None)
        if callable(close_dialog):
            close_dialog()
        refresh_map = getattr(self, "_refresh_fleet_map_fields", None)
        if callable(refresh_map):
            refresh_map()

    def sync_map_selection_from_storage(
        self,
        key: str,
        old_value: str,
        new_value: str,
        url: str,
    ):
        if key == FleetService.MAP_SELECTION_STORAGE_KEY:
            raw_value = str(new_value).strip()
            if not raw_value:
                return

            selected_device_id = raw_value.split("::", 1)[0].strip()
            if not selected_device_id:
                return

            self.selected_device_id = selected_device_id
            self.monitor_view = "intersection"
            close_dialog = getattr(self, "close_controller_profile_creation_dialog", None)
            if callable(close_dialog):
                close_dialog()
            refresh_map = getattr(self, "_refresh_fleet_map_fields", None)
            if callable(refresh_map):
                refresh_map()
            return

        if key != FleetService.MAP_CREATE_STORAGE_KEY:
            return

        raw_value = str(new_value).strip()
        if not raw_value:
            return

        try:
            payload = json.loads(raw_value)
        except json.JSONDecodeError:
            return

        if not isinstance(payload, dict):
            return

        latitude = payload.get("latitude")
        longitude = payload.get("longitude")
        if latitude is None or longitude is None:
            return

        try:
            latitude_value = float(latitude)
            longitude_value = float(longitude)
        except (TypeError, ValueError):
            return

        open_dialog = getattr(self, "open_controller_profile_creation_from_map_point", None)
        if callable(open_dialog):
            open_dialog(latitude_value, longitude_value)

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

    def _selected_device_target(self) -> tuple[str, str, DeviceConfig]:
        profiles = self._fleet_profiles()
        return FleetService.resolve_target(
            profiles=profiles,
            selected_device_id=self.selected_device_id,
            fallback_config=self._build_config(),
            fallback_device_id=self.ip_address.strip() or "single-device",
            fallback_device_type=FleetService.DEFAULT_DEVICE_TYPE,
        )

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

    async def _collect_selected_connection_status(self) -> tuple[str, str, dict, int]:
        device_type, device_id, config = self._selected_device_target()
        payload, mp_model = await PollingService.collect_connection_status(
            device_type,
            config,
            device_id=device_id,
        )
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
        except Exception as exc:
            self.m60_status = {"error": f"Unhandled exception: {exc}"}
            self.m60_status_json = json.dumps(self.m60_status, indent=2)
            self.error = self.m60_status["error"]
            self.status_text = "Unhandled exception"
            self.is_online = False
        finally:
            self.is_loading = False

    async def connect_m60(self):
        self.is_loading = True
        try:
            try:
                device_id, device_type, status_payload, mp_model = await self._collect_selected_connection_status()
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
        except Exception as exc:
            self.m60_status = {"error": f"Unhandled exception: {exc}"}
            self.m60_status_json = json.dumps(self.m60_status, indent=2)
            self.error = self.m60_status["error"]
            self.status_text = "Unhandled exception"
            self.is_online = False
        finally:
            self.is_loading = False

        if (self.auto_refresh_enabled or self.auto_reconnect_enabled) and not self.auto_refresh_running:
            return type(self).auto_refresh_loop

    async def refresh_status(self):
        await self.add_and_poll_m60()

    async def connect_and_start_polling(self):
        self.refresh_runtime_health()
        self.refresh_runtime_registry_status()
        return await self.connect_m60()