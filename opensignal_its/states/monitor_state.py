"""Single-controller monitor and snapshot state slice."""

from __future__ import annotations

import json
import asyncio
from typing import Any

import reflex as rx

from ..devices.base import Device
from ..devices.parsers import build_siemens_m60_view
from ..db import STORE
from ..models.device import DeviceConfig
from ..models.media import MediaStreamConfig
from ..protocols.rtsp import redact_rtsp_url, sanitize_rtsp_value
from ..services import FleetService, MediaService, PollingService


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
    selected_controller_command_capabilities: list[dict[str, Any]] = []
    selected_controller_command_notice: str = "Select a controller to view command capabilities."
    selected_controller_connection_notice: str = ""
    selected_controller_connection_notice_scheme: str = "gray"
    selected_controller_live_refresh_running: bool = False
    selected_controller_pattern_action_rows: list[dict[str, str]] = []
    selected_controller_mode_action_rows: list[dict[str, str]] = []
    selected_controller_supports_select_pattern: bool = False
    selected_controller_supports_set_mode: bool = False
    selected_controller_supports_manual_hold: bool = False
    selected_controller_supports_advance_phase: bool = False
    selected_controller_media_streams: list[dict[str, Any]] = []
    selected_controller_media_statuses: list[dict[str, Any]] = []
    selected_controller_media_rows: list[dict[str, Any]] = []
    selected_controller_media_notice: str = "Select a controller to view media streams."
    selected_controller_media_loading: bool = False

    def _clear_selected_controller_command_state(self, notice: str):
        self.selected_controller_command_capabilities = []
        self.selected_controller_pattern_action_rows = []
        self.selected_controller_mode_action_rows = []
        self.selected_controller_supports_select_pattern = False
        self.selected_controller_supports_set_mode = False
        self.selected_controller_supports_manual_hold = False
        self.selected_controller_supports_advance_phase = False
        self.selected_controller_command_notice = notice

    def _command_quick_action_rows(
        self,
        command_id: str,
        action_by_value: dict[Any, tuple[str, str]],
    ) -> list[dict[str, str]]:
        capability = next(
            (
                item
                for item in self.selected_controller_command_capabilities
                if str(item.get("command_id", "")).strip() == command_id
            ),
            {},
        )

        rows: list[dict[str, str]] = []
        seen_action_ids: set[str] = set()

        raw_options = capability.get("options", [])
        if isinstance(raw_options, list):
            for option in raw_options:
                if not isinstance(option, dict):
                    continue
                action = action_by_value.get(option.get("value"))
                if action is None:
                    continue
                action_id, fallback_label = action
                if action_id in seen_action_ids:
                    continue
                label = str(option.get("label", "")).strip() or fallback_label
                rows.append({"action_id": action_id, "label": label})
                seen_action_ids.add(action_id)

        if rows:
            return rows

        raw_allowed_values = capability.get("allowed_values", [])
        if not isinstance(raw_allowed_values, list):
            return []

        for value in raw_allowed_values:
            action = action_by_value.get(value)
            if action is None:
                continue
            action_id, fallback_label = action
            if action_id in seen_action_ids:
                continue
            rows.append({"action_id": action_id, "label": fallback_label})
            seen_action_ids.add(action_id)

        return rows

    def _normalize_command_capability_payload(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        raw_commands = payload.get("command_capabilities", [])
        if not isinstance(raw_commands, list):
            return []

        normalized: list[dict[str, Any]] = []
        seen_command_ids: set[str] = set()
        for item in raw_commands:
            if not isinstance(item, dict):
                continue
            command_id = str(item.get("command_id", "")).strip()
            if not command_id or command_id in seen_command_ids:
                continue
            seen_command_ids.add(command_id)

            raw_options = item.get("options", [])
            normalized_options: list[dict[str, Any]] = []
            if isinstance(raw_options, list):
                for option in raw_options:
                    if not isinstance(option, dict):
                        continue
                    label = str(option.get("label", "")).strip()
                    value = option.get("value")
                    if not label and value is None:
                        continue
                    normalized_options.append(
                        {
                            "label": label or str(value),
                            "value": value,
                        }
                    )

            raw_allowed_values = item.get("allowed_values", [])
            normalized_allowed_values = (
                list(raw_allowed_values)
                if isinstance(raw_allowed_values, list)
                else []
            )
            raw_value_schema = item.get("value_schema")
            normalized_value_schema = (
                dict(raw_value_schema)
                if isinstance(raw_value_schema, dict)
                else {}
            )

            normalized.append(
                {
                    "command_id": command_id,
                    "requires_confirmation": bool(item.get("requires_confirmation", False)),
                    "requires_value": bool(item.get("requires_value", False)),
                    "value_type": str(item.get("value_type", "")).strip(),
                    "allowed_values": normalized_allowed_values,
                    "options": normalized_options,
                    "value_schema": normalized_value_schema,
                }
            )
        return normalized

    def _refresh_selected_controller_command_state(self, notice: str = "") -> list[dict[str, Any]]:
        target_device_id = str(self.selected_device_id).strip()
        if not target_device_id:
            self._clear_selected_controller_command_state(
                notice or "Select a controller to view command capabilities."
            )
            return []

        fleet_profiles = getattr(self, "_fleet_profiles", None)
        if not callable(fleet_profiles):
            self._clear_selected_controller_command_state(
                notice or "Command capabilities are unavailable for the selected controller."
            )
            return []

        try:
            profiles = fleet_profiles()
            selected_profile = FleetService.select_profile(profiles, target_device_id)
            if not selected_profile or str(selected_profile.get("device_id", "")).strip() != target_device_id:
                self._clear_selected_controller_command_state(
                    notice or "No controller profile is loaded for the selected controller."
                )
                return []

            device_type = (
                str(selected_profile.get("device_type", FleetService.DEFAULT_DEVICE_TYPE)).strip()
                or FleetService.DEFAULT_DEVICE_TYPE
            )
            device = Device.create(device_type, FleetService.build_device_config(selected_profile))
            capability_payload = device.get_capabilities()
        except Exception:
            self._clear_selected_controller_command_state(
                notice or "Command capabilities are unavailable for the selected controller."
            )
            return []

        capabilities = self._normalize_command_capability_payload(
            capability_payload if isinstance(capability_payload, dict) else {}
        )
        self.selected_controller_command_capabilities = capabilities

        supported_command_ids = {
            str(item.get("command_id", "")).strip()
            for item in capabilities
            if str(item.get("command_id", "")).strip()
        }
        self.selected_controller_supports_select_pattern = "select_pattern" in supported_command_ids
        self.selected_controller_supports_set_mode = "set_mode" in supported_command_ids
        self.selected_controller_supports_manual_hold = "manual_hold" in supported_command_ids
        self.selected_controller_supports_advance_phase = "advance_phase" in supported_command_ids
        self.selected_controller_pattern_action_rows = self._command_quick_action_rows(
            "select_pattern",
            {
                1: ("select_pattern_1", "Pattern 1"),
                2: ("select_pattern_2", "Pattern 2"),
            },
        )
        self.selected_controller_mode_action_rows = self._command_quick_action_rows(
            "set_mode",
            {
                "free": ("set_mode_free", "Free"),
                "coordinated": ("set_mode_coordinated", "Coord"),
            },
        )

        if notice:
            self.selected_controller_command_notice = notice
        elif not capabilities:
            self.selected_controller_command_notice = (
                "Command capabilities are unavailable for the selected controller."
            )
        else:
            capability_label = "command capability" if len(capabilities) == 1 else "command capabilities"
            self.selected_controller_command_notice = (
                f"{len(capabilities)} {capability_label} available for {target_device_id}."
            )
        return capabilities

    def _safe_media_stream_config(self, stream_config: MediaStreamConfig) -> dict[str, Any]:
        safe_url = redact_rtsp_url(stream_config.url)
        try:
            safe_url = MediaService.validate_stream_config(stream_config).safe_url
        except ValueError:
            pass

        metadata = sanitize_rtsp_value(stream_config.metadata, stream_config.url, safe_url)
        metadata_text = ""
        if metadata:
            metadata_text = ", ".join(
                f"{key}: {value}"
                for key, value in metadata.items()
            )

        return {
            "stream_id": stream_config.stream_id,
            "name": stream_config.name,
            "enabled": bool(stream_config.enabled),
            "enabled_label": "Enabled" if stream_config.enabled else "Disabled",
            "enabled_scheme": "green" if stream_config.enabled else "gray",
            "timeout_seconds": float(stream_config.timeout_seconds),
            "timeout_text": f"{float(stream_config.timeout_seconds):g}s timeout",
            "safe_url": safe_url,
            "metadata": metadata,
            "metadata_text": metadata_text,
        }

    def _build_selected_controller_media_rows(self) -> list[dict[str, Any]]:
        status_by_stream_id = {
            str(status.get("stream_id", "")).strip(): dict(status)
            for status in self.selected_controller_media_statuses
            if str(status.get("stream_id", "")).strip()
        }
        rows: list[dict[str, Any]] = []
        for stream in self.selected_controller_media_streams:
            status = dict(status_by_stream_id.get(str(stream.get("stream_id", "")).strip(), {}))
            checked_at = str(status.get("checked_at", "")).strip()
            is_checked = bool(status)
            is_online = bool(status.get("is_online", False))
            status_scheme = "gray"
            status_label = "Not Checked"
            if is_checked and is_online:
                status_scheme = "green"
                status_label = "Online"
            elif is_checked:
                status_scheme = "red"
                status_label = "Offline"

            latency_ms = status.get("latency_ms")
            latency_text = ""
            if latency_ms is not None:
                latency_text = f"{latency_ms} ms"

            error_text = "; ".join(str(error) for error in status.get("errors", []))
            checked_text = f"Checked {checked_at}" if checked_at else "Not checked yet."
            rows.append(
                {
                    **dict(stream),
                    "status_text": str(status.get("status_text", "Not checked yet.")),
                    "status_label": status_label,
                    "status_scheme": status_scheme,
                    "checked_text": checked_text,
                    "latency_text": latency_text,
                    "error_text": error_text,
                }
            )
        return rows

    def _refresh_selected_controller_media_state(self, notice: str = "") -> list[MediaStreamConfig]:
        target_device_id = str(self.selected_device_id).strip()
        if not target_device_id:
            self.selected_controller_media_streams = []
            self.selected_controller_media_statuses = []
            self.selected_controller_media_rows = []
            self.selected_controller_media_notice = notice or "Select a controller to view media streams."
            return []

        fleet_profiles = getattr(self, "_fleet_profiles", None)
        if not callable(fleet_profiles):
            self.selected_controller_media_streams = []
            self.selected_controller_media_statuses = []
            self.selected_controller_media_rows = []
            self.selected_controller_media_notice = notice or "Media streams are unavailable for the selected controller."
            return []

        try:
            profiles = fleet_profiles()
            selected_profile = FleetService.select_profile(profiles, target_device_id)
            if not selected_profile:
                self.selected_controller_media_streams = []
                self.selected_controller_media_statuses = []
                self.selected_controller_media_rows = []
                self.selected_controller_media_notice = notice or "No controller profile is loaded for the selected controller."
                return []
            stream_configs = FleetService.media_stream_configs(selected_profile)
        except Exception:
            self.selected_controller_media_streams = []
            self.selected_controller_media_statuses = []
            self.selected_controller_media_rows = []
            self.selected_controller_media_notice = notice or "Media stream configuration is unavailable for the selected controller."
            return []

        status_by_stream_id = {
            str(status.get("stream_id", "")).strip(): dict(status)
            for status in self.selected_controller_media_statuses
            if str(status.get("stream_id", "")).strip()
        }
        self.selected_controller_media_streams = [
            self._safe_media_stream_config(stream_config)
            for stream_config in stream_configs
        ]
        self.selected_controller_media_statuses = [
            status_by_stream_id[stream_config.stream_id]
            for stream_config in stream_configs
            if stream_config.stream_id in status_by_stream_id
        ]
        self.selected_controller_media_rows = self._build_selected_controller_media_rows()
        if notice:
            self.selected_controller_media_notice = notice
        elif not stream_configs:
            self.selected_controller_media_notice = "No media streams configured for the selected controller."
        else:
            stream_label = "stream" if len(stream_configs) == 1 else "streams"
            self.selected_controller_media_notice = (
                f"{len(stream_configs)} media {stream_label} configured for {target_device_id}."
            )
        return stream_configs

    def update_ip_address(self, value: str):
        self.ip_address = value

    def update_port_text(self, value: str):
        self.port_text = value

    def update_community(self, value: str):
        self.community = value

    def update_snmp_version(self, value: str):
        self.snmp_version = value

    def _clear_selected_controller_connection_notice(self):
        self.selected_controller_connection_notice = ""
        self.selected_controller_connection_notice_scheme = "gray"

    def _reset_selected_controller_live_detail_state(self):
        self.m60_status = {}
        self.m60_status_json = ""
        self.status_text = "No status yet"
        self.active_snmp_version = "unknown"
        self.current_pattern = "Unknown"
        self.unit_status = "unknown"
        self.green_phases = "none"
        self.yellow_phases = "none"
        self.red_phases = "none"
        self.vehicle_calls = "none"
        self.ped_calls = "none"
        self.remaining_time_summary = "none"
        self.timer_mode_text = "unknown"
        self.ring_status_summary = "unknown"
        self.ring_status_lines = []
        self.ring_status_console_text = "RING STATUS CONSOLE\n(no data)"
        self.last_ring_status_raw = {}
        self.ring_state_age_seconds = {}
        self.phase_data = {}
        self.phase_current_pattern = "Unknown"
        self.phase_unit_control_status = "unknown"
        self.phase_detail_lines = []
        self.last_timer_snapshot = {}
        self.phase_state_age_seconds = {}
        self.last_phase_state_signature = {}
        self.is_online = False
        self.last_updated = ""
        if hasattr(self, "error"):
            self.error = ""
        self._clear_selected_controller_connection_notice()

    def update_selected_device_id(self, value: str):
        if str(value).strip() != self.selected_device_id.strip():
            self._reset_selected_controller_live_detail_state()
        self.selected_device_id = value
        self._refresh_selected_controller_command_state()
        self._refresh_selected_controller_media_state()
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
        self._refresh_selected_controller_command_state()
        self._refresh_selected_controller_media_state()

    def back_to_dashboard(self):
        self.monitor_view = "dashboard"
        refresh_cards = getattr(self, "_refresh_fleet_card_fields", None)
        if callable(refresh_cards):
            refresh_cards()
        refresh_map = getattr(self, "_refresh_fleet_map_fields", None)
        if callable(refresh_map):
            refresh_map()
        refresh_aggregates = getattr(self, "_refresh_fleet_aggregate_fields", None)
        if callable(refresh_aggregates):
            refresh_aggregates()

    async def _select_controller_from_device_id(self, device_id: str):
        normalized_device_id = str(device_id).strip()
        if not normalized_device_id:
            return

        if normalized_device_id != self.selected_device_id.strip():
            self._reset_selected_controller_live_detail_state()
        self.selected_device_id = normalized_device_id
        self.monitor_view = "intersection"
        load_profile = getattr(self, "load_controller_profile_from_row", None)
        if callable(load_profile):
            load_profile(normalized_device_id)
        self._refresh_selected_controller_command_state()
        self._refresh_selected_controller_media_state()
        close_dialog = getattr(self, "close_controller_profile_creation_dialog", None)
        if callable(close_dialog):
            close_dialog()
        refresh_map = getattr(self, "_refresh_fleet_map_fields", None)
        if callable(refresh_map):
            refresh_map()
        return self._selected_controller_live_refresh_event()

    def _selected_controller_live_refresh_event(self):
        if not bool(getattr(self, "controller_profile_form_polling_enabled", False)):
            if hasattr(self, "auto_refresh_enabled"):
                self.auto_refresh_enabled = False
            return None

        if hasattr(self, "auto_refresh_enabled"):
            self.auto_refresh_enabled = True
        if hasattr(self, "auto_reconnect_enabled"):
            self.auto_reconnect_enabled = True
        if hasattr(self, "managed_polling_notice"):
            target = self.selected_device_id.strip() or "selected controller"
            interval_seconds = ""
            refresh_interval = getattr(self, "_refresh_interval_seconds", None)
            if callable(refresh_interval):
                interval_seconds = f" every {refresh_interval():g}s"
            self.managed_polling_notice = f"Live updates enabled for {target}; refreshing{interval_seconds}."

        live_refresh_handler = getattr(type(self), "selected_controller_live_refresh_loop", None)
        if callable(live_refresh_handler) and getattr(live_refresh_handler, "is_background", False):
            return live_refresh_handler()
        return None

    def _set_selected_live_refresh_notice(
        self,
        device_id: str,
        status_payload: dict[str, Any],
        interval_seconds: float,
    ):
        errors = status_payload.get("errors", [])
        has_errors = bool(errors) if isinstance(errors, list) else bool(errors)
        is_online = bool(status_payload.get("is_online", False))
        if is_online and not has_errors:
            self.managed_polling_notice = (
                f"Live refresh updated {device_id}; next refresh in {interval_seconds:g}s."
            )
            return

        status_text = str(status_payload.get("status_text", "offline")).strip() or "offline"
        raw_extra = status_payload.get("extra", {})
        extra = raw_extra if isinstance(raw_extra, dict) else {}
        raw_backoff = extra.get("poll_backoff", {})
        backoff = raw_backoff if isinstance(raw_backoff, dict) else {}
        failure_streak = backoff.get("failure_streak")
        failure_text = ""
        if failure_streak:
            failure_text = f" after {failure_streak} consecutive failures"

        if bool(backoff.get("active", False)) and bool(backoff.get("skipped", False)):
            if not self.selected_controller_connection_notice:
                self.selected_controller_connection_notice = (
                    f"Live polling is not getting through; using the last snapshot{failure_text}."
                )
                self.selected_controller_connection_notice_scheme = "amber"
            self.managed_polling_notice = (
                f"Live polling is not getting through to {device_id}; "
                f"using the last snapshot{failure_text}, retrying in {interval_seconds:g}s."
            )
        else:
            if not self.selected_controller_connection_notice:
                self.selected_controller_connection_notice = (
                    f"Live polling is not getting through: {status_text}."
                )
                self.selected_controller_connection_notice_scheme = "tomato"
            self.managed_polling_notice = (
                f"Live polling is not getting through to {device_id}: {status_text}; "
                f"retrying in {interval_seconds:g}s."
            )

    @rx.event(background=True)
    async def selected_controller_live_refresh_loop(self):
        async with self:
            if self.selected_controller_live_refresh_running:
                return
            self.selected_controller_live_refresh_running = True

        try:
            while True:
                async with self:
                    refresh_enabled = bool(getattr(self, "auto_refresh_enabled", False))
                    selected_device_id = self.selected_device_id.strip()
                    monitor_view = self.monitor_view
                    interval_seconds = self._refresh_interval_seconds()
                    if not refresh_enabled or not selected_device_id or monitor_view != "intersection":
                        break
                    try:
                        device_type, device_id, config = self._selected_device_target()
                    except Exception as exc:
                        self.managed_polling_notice = f"Live refresh paused: {exc}"
                        self.error = str(exc)
                        break

                try:
                    payload, mp_model = await PollingService.collect_snapshot(
                        device_type,
                        config,
                        device_id=device_id,
                    )
                except Exception as exc:
                    result_is_current = False
                    async with self:
                        result_is_current = self.selected_device_id.strip() == selected_device_id
                        if result_is_current:
                            self.status_text = "Live refresh failed"
                            self.error = str(exc)
                            self.selected_controller_connection_notice = f"Live refresh failed: {exc}"
                            self.selected_controller_connection_notice_scheme = "tomato"
                            self.managed_polling_notice = (
                                f"Live polling is not getting through to {selected_device_id}: {exc}; "
                                f"retrying in {interval_seconds:g}s."
                            )
                    if not result_is_current:
                        continue
                else:
                    result_is_current = False
                    async with self:
                        result_is_current = self.selected_device_id.strip() == selected_device_id
                        if result_is_current:
                            self._apply_selected_status_result(
                                device_id,
                                device_type,
                                payload,
                                mp_model,
                            )
                            self._set_selected_live_refresh_notice(
                                device_id,
                                payload,
                                interval_seconds,
                            )
                            refresh_runtime_registry = getattr(self, "refresh_runtime_registry_status", None)
                            if callable(refresh_runtime_registry):
                                refresh_runtime_registry()
                    if not result_is_current:
                        continue

                await asyncio.sleep(interval_seconds)
        finally:
            async with self:
                self.selected_controller_live_refresh_running = False

    async def select_controller_from_row(self, row: str):
        tokenized = row.strip().split()
        if tokenized:
            return await self._select_controller_from_device_id(tokenized[0])
        return None

    async def select_controller_from_map_points(self, points: list[dict[str, Any]]):
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

        return await self._select_controller_from_device_id(device_id)

    async def sync_map_selection_from_storage(
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

            return await self._select_controller_from_device_id(selected_device_id)

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

        select_map_point = getattr(self, "select_controller_profile_map_point", None)
        if callable(select_map_point):
            select_map_point(latitude_value, longitude_value)

        update_form_latitude = getattr(self, "update_controller_profile_form_latitude_text", None)
        update_form_longitude = getattr(self, "update_controller_profile_form_longitude_text", None)
        dialog_open = bool(getattr(self, "controller_profile_creation_dialog_open", False))
        if dialog_open and callable(update_form_latitude) and callable(update_form_longitude):
            formatted_latitude = f"{float(latitude_value):.6f}".rstrip("0").rstrip(".")
            formatted_longitude = f"{float(longitude_value):.6f}".rstrip("0").rstrip(".")
            update_form_latitude(formatted_latitude)
            update_form_longitude(formatted_longitude)

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

    def _apply_status_snapshot(
        self,
        status_payload: dict,
        mp_model: int,
        *,
        correlation_id: str = "",
        source: str = "poll",
        status_text_default: str = "Unknown",
    ):
        """Apply one status snapshot to state fields used by the UI."""
        previous_updated = self.last_updated
        self.m60_status = status_payload
        self.m60_status_json = json.dumps(self.m60_status, indent=2)
        self.status_text = str(self.m60_status.get("status_text", status_text_default))
        self.is_online = bool(self.m60_status.get("is_online", False))
        self.last_updated = str(self.m60_status.get("timestamp", ""))
        poll_delta_seconds = self._poll_delta_seconds(previous_updated, self.last_updated)
        self._apply_phase_payload(self.m60_status, poll_delta_seconds)
        self.active_snmp_version = "v2c" if mp_model == 1 else "v1"
        raw_errors = self.m60_status.get("errors", [])
        errors = raw_errors if isinstance(raw_errors, list) else []
        self.error = "; ".join(errors) if errors else ""
        lower_status_text = self.status_text.strip().lower()
        error_blob = self.error.lower()
        raw_extra = self.m60_status.get("extra", {})
        extra = raw_extra if isinstance(raw_extra, dict) else {}
        raw_backoff = extra.get("poll_backoff", {})
        backoff = raw_backoff if isinstance(raw_backoff, dict) else {}
        backoff_active = bool(backoff.get("active", False))
        backoff_skipped = bool(backoff.get("skipped", False))
        backoff_streak = backoff.get("failure_streak")
        if not self.is_online or self.error:
            if backoff_active:
                if backoff_skipped:
                    self.selected_controller_connection_notice = (
                        "Backoff active: using stale snapshot "
                        f"after {backoff_streak} consecutive failures."
                    )
                    self.selected_controller_connection_notice_scheme = "amber"
                else:
                    self.selected_controller_connection_notice = (
                        "Backoff scheduled: "
                        f"{backoff_streak} consecutive failures detected."
                    )
                    self.selected_controller_connection_notice_scheme = "amber"
            elif lower_status_text.startswith("snmpv1 connection failed"):
                if "no response from sysdescr/currentpattern" in error_blob:
                    self.selected_controller_connection_notice = (
                        "SNMP transport failure: connect probe got no response "
                        "from sysDescr/currentPattern."
                    )
                    self.selected_controller_connection_notice_scheme = "tomato"
                elif "timeout" in error_blob:
                    self.selected_controller_connection_notice = "SNMP timeout during connect."
                    self.selected_controller_connection_notice_scheme = "tomato"
                else:
                    self.selected_controller_connection_notice = f"Connection failed: {self.status_text}"
                    self.selected_controller_connection_notice_scheme = "tomato"
            elif lower_status_text.startswith("snmp connect exception"):
                self.selected_controller_connection_notice = "SNMP connect exception: check modem or link stability."
                self.selected_controller_connection_notice_scheme = "tomato"
            elif lower_status_text.startswith("snmpv1 poll failed") or lower_status_text.startswith("snmpv1 poll exception"):
                if "no values returned from known-good oids" in error_blob:
                    self.selected_controller_connection_notice = (
                        "SNMP poll failure: no values returned from known-good OIDs."
                    )
                    self.selected_controller_connection_notice_scheme = "tomato"
                elif "timeout" in error_blob:
                    self.selected_controller_connection_notice = "SNMP timeout during poll."
                    self.selected_controller_connection_notice_scheme = "tomato"
                else:
                    self.selected_controller_connection_notice = f"Poll failed: {self.status_text}"
                    self.selected_controller_connection_notice_scheme = "tomato"
            elif self.error:
                self.selected_controller_connection_notice = f"Device error: {self.error}"
                self.selected_controller_connection_notice_scheme = "tomato"
            else:
                self.selected_controller_connection_notice = f"Connection state: {self.status_text}"
                self.selected_controller_connection_notice_scheme = "gray"
        else:
            self.selected_controller_connection_notice = ""
            self.selected_controller_connection_notice_scheme = "gray"
        self._safe_log_status_snapshot(status_payload, correlation_id=correlation_id, source=source)

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
            self._apply_selected_status_result(device_id, device_type, status_payload, mp_model)
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
            self._apply_selected_status_result(device_id, device_type, status_payload, mp_model)
        except Exception as exc:
            self.m60_status = {"error": f"Unhandled exception: {exc}"}
            self.m60_status_json = json.dumps(self.m60_status, indent=2)
            self.error = self.m60_status["error"]
            self.status_text = "Unhandled exception"
            self.is_online = False
        finally:
            self.is_loading = False

    async def refresh_status(self):
        async with self:
            self.managed_polling_notice = "Refreshing selected controller once..."
            await self.add_and_poll_m60()
            self.managed_polling_notice = "Refreshed selected controller once."

    async def connect_and_start_polling(self):
        self.refresh_runtime_health()
        self.refresh_runtime_registry_status()
        self.managed_polling_notice = "Connecting and starting managed polling..."
        await self.connect_m60()
        started = await self.start_selected_managed_polling()
        if hasattr(self, "auto_refresh_enabled"):
            self.auto_refresh_enabled = bool(started)
        if hasattr(self, "auto_reconnect_enabled"):
            self.auto_reconnect_enabled = bool(started)
        live_refresh_handler = getattr(type(self), "selected_controller_live_refresh_loop", None)
        if started and getattr(live_refresh_handler, "is_background", False):
            return live_refresh_handler()

    async def refresh_selected_controller_media_stream_health(self):
        self.selected_controller_media_loading = True
        try:
            stream_configs = self._refresh_selected_controller_media_state()
            if not stream_configs:
                return

            stream_label = "stream" if len(stream_configs) == 1 else "streams"
            self.selected_controller_media_notice = (
                f"Checking {len(stream_configs)} media {stream_label} for {self.selected_device_id.strip()}..."
            )
            statuses: list[dict[str, Any]] = []
            for stream_config in stream_configs:
                status = await MediaService.describe_stream_protocol(stream_config)
                statuses.append(status.model_dump(mode="json"))
            self.selected_controller_media_statuses = statuses
            self.selected_controller_media_rows = self._build_selected_controller_media_rows()
            self.selected_controller_media_notice = (
                f"Checked {len(stream_configs)} media {stream_label} for {self.selected_device_id.strip()}."
            )
        except Exception:
            self.selected_controller_media_statuses = []
            self.selected_controller_media_rows = self._build_selected_controller_media_rows()
            self.selected_controller_media_notice = "Media health check failed for the selected controller."
        finally:
            self.selected_controller_media_loading = False