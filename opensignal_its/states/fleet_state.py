"""Fleet status refresh and auto-refresh state slice."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import reflex as rx

from ..models.fleet import FleetRefreshView, FleetSnapshotEntry
from ..polling_telemetry import POLLING_TELEMETRY
from ..services import FleetService, PollingService


def _fleet_status_cards(status_by_id: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    cards: list[dict[str, str]] = []
    for device_id, raw_status in status_by_id.items():
        device_type = str(raw_status.get("device_type", "unknown") or "unknown")
        is_online = bool(raw_status.get("is_online", False))
        timestamp = str(raw_status.get("timestamp", "") or "")
        cards.append(
            {
                "device_id": str(device_id),
                "device_type": device_type,
                "device_type_label": device_type.replace("_", " ").upper(),
                "status_label": "Online" if is_online else "Offline",
                "status_scheme": "green" if is_online else "red",
                "status_text": str(raw_status.get("status_text", "unknown") or "unknown"),
                "updated_text": f"Updated {timestamp}" if timestamp else "Awaiting refresh",
            }
        )
    return cards


def _fleet_view_to_state_fields(refresh_view: FleetRefreshView) -> dict[str, Any]:
    selected_device_id = str(refresh_view.selected_device_id)
    status_by_id = {
        key: value.model_dump(mode="json")
        for key, value in refresh_view.status_by_id.items()
    }
    return {
        "selected_device_id": selected_device_id,
        "fleet_status_by_id": status_by_id,
        "fleet_status_cards": _fleet_status_cards(status_by_id),
        "fleet_device_rows": list(refresh_view.rows),
        "selected_payload": refresh_view.selected_payload,
        "selected_mp_model": int(refresh_view.selected_mp_model),
        "selected_device_type": str(refresh_view.selected_device_type),
    }


class FleetStateMixin(rx.State, mixin=True):
    fleet_status_summary: str = "Controller view idle."
    fleet_device_rows: list[str] = []
    fleet_status_by_id: dict[str, dict[str, Any]] = {}
    fleet_status_cards: list[dict[str, str]] = []
    fleet_status_mapping_filter: str = "all"
    fleet_status_card_notice: str = "No controller profiles are configured yet."
    fleet_map_markers: list[dict[str, Any]] = []
    fleet_unmapped_device_ids: list[str] = []
    fleet_unmapped_profile_rows: list[dict[str, str]] = []
    fleet_map_data: list[dict[str, Any]] = []
    fleet_map_layout: dict[str, Any] = {}
    fleet_map_figure: dict[str, Any] = {}
    fleet_map_src_doc: str = FleetService.build_map_src_doc([], "")
    fleet_map_notice: str = "Add controller coordinates to place signals on the map."
    fleet_online_count: int = 0
    fleet_offline_count: int = 0
    fleet_total_count: int = 0
    auto_refresh_enabled: bool = False
    refresh_interval_text: str = "5"
    auto_reconnect_enabled: bool = True
    reconnect_interval_text: str = "10"
    auto_refresh_running: bool = False

    def update_auto_refresh_enabled(self, value: bool):
        self.auto_refresh_enabled = value

    def update_refresh_interval_text(self, value: str):
        self.refresh_interval_text = value

    def update_auto_reconnect_enabled(self, value: bool):
        self.auto_reconnect_enabled = value

    def update_reconnect_interval_text(self, value: str):
        self.reconnect_interval_text = value

    def update_fleet_status_mapping_filter(self, value: str):
        normalized = value.strip().lower()
        if normalized not in {"all", "mapped", "unmapped"}:
            return
        self.fleet_status_mapping_filter = normalized
        self._refresh_fleet_card_fields()

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

    def _fleet_profiles(self) -> list[dict[str, Any]]:
        return FleetService.parse_profiles_json(self.device_profiles_json)

    def _refresh_fleet_card_fields(self, profiles: list[dict[str, Any]] | None = None):
        if profiles is None:
            try:
                profiles = self._fleet_profiles()
            except Exception:
                profiles = []
        visible_profiles = FleetService.filter_profiles_by_mapping(
            profiles,
            self.fleet_status_mapping_filter,
        )
        self.fleet_status_cards = FleetService.build_profile_display_rows(
            visible_profiles,
            self.fleet_status_by_id,
        )
        visible_count = len(visible_profiles)
        controller_label = "controller" if visible_count == 1 else "controllers"
        if not profiles:
            self.fleet_status_card_notice = "No controller profiles are configured yet."
        elif self.fleet_status_mapping_filter == "mapped":
            if visible_count:
                self.fleet_status_card_notice = f"Showing {visible_count} mapped {controller_label}."
            else:
                self.fleet_status_card_notice = "No controllers have coordinates yet."
        elif self.fleet_status_mapping_filter == "unmapped":
            if visible_count:
                self.fleet_status_card_notice = (
                    f"Showing {visible_count} {controller_label} needing coordinates."
                )
            else:
                self.fleet_status_card_notice = "All configured controllers already have coordinates."
        else:
            self.fleet_status_card_notice = (
                f"Showing all {visible_count} configured {controller_label}."
            )

    def _refresh_fleet_map_fields(self, profiles: list[dict[str, Any]] | None = None):
        if profiles is None:
            try:
                profiles = self._fleet_profiles()
            except Exception:
                profiles = []

        markers = FleetService.build_map_marker_rows(
            profiles,
            self.fleet_status_by_id,
            self.selected_device_id,
        )
        unmapped_profiles = FleetService.filter_profiles_by_mapping(profiles, "unmapped")
        unmapped = FleetService.list_unmapped_profiles(unmapped_profiles)
        self.fleet_map_markers = markers
        self.fleet_unmapped_device_ids = unmapped
        self.fleet_unmapped_profile_rows = FleetService.build_profile_display_rows(
            unmapped_profiles,
            self.fleet_status_by_id,
        )
        self.fleet_map_data = FleetService.build_map_data(markers)
        self.fleet_map_layout = FleetService.build_map_layout(markers)
        self.fleet_map_figure = {
            "data": list(self.fleet_map_data),
            "layout": dict(self.fleet_map_layout),
        }
        self.fleet_map_src_doc = FleetService.build_map_src_doc(
            markers,
            self.selected_device_id,
        )

        if not profiles:
            self.fleet_map_notice = "No controller profiles are configured yet."
        elif markers and unmapped:
            self.fleet_map_notice = (
                f"Showing {len(markers)} mapped controllers; {len(unmapped)} still need coordinates."
            )
        elif markers:
            self.fleet_map_notice = f"Showing {len(markers)} mapped controllers."
        else:
            self.fleet_map_notice = (
                "Add latitude and longitude in Controllers to place signals on the map."
            )

    def _refresh_fleet_aggregate_fields(self, profiles: list[dict[str, Any]] | None = None):
        if profiles is None:
            try:
                profiles = self._fleet_profiles()
            except Exception:
                profiles = []

        profile_ids = {
            str(profile.get("device_id", "")).strip()
            for profile in profiles
            if str(profile.get("device_id", "")).strip()
        }
        status_by_id = dict(self.fleet_status_by_id)
        total = len(profile_ids) if profile_ids else len(status_by_id)
        known_statuses = [
            payload
            for device_id, payload in status_by_id.items()
            if not profile_ids or device_id in profile_ids
        ]
        online = sum(1 for payload in known_statuses if bool(payload.get("is_online", False)))
        offline = sum(
            1
            for payload in known_statuses
            if "is_online" in payload and not bool(payload.get("is_online", False))
        )
        awaiting_refresh = max(0, total - len(known_statuses))

        self.fleet_total_count = total
        self.fleet_online_count = online
        self.fleet_offline_count = offline
        if total > 0:
            summary = f"Controllers: {total} configured, {online} online, {offline} offline"
            if awaiting_refresh:
                summary = f"{summary}, {awaiting_refresh} awaiting refresh"
            self.fleet_status_summary = f"{summary}."

    def _cache_device_status(self, device_id: str, device_type: str, payload: dict[str, Any]):
        cache = dict(self.fleet_status_by_id)
        cache[device_id] = {
            "device_type": device_type,
            "is_online": bool(payload.get("is_online", False)),
            "status_text": str(payload.get("status_text", "unknown")),
            "timestamp": str(payload.get("timestamp", "")),
        }
        self.fleet_status_by_id = cache
        self._refresh_fleet_card_fields()

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
        self._refresh_fleet_map_fields()
        self._refresh_fleet_aggregate_fields()
        self._sync_controller_profile_rows()

    def _apply_selected_status_result(
        self,
        device_id: str,
        device_type: str,
        status_payload: dict[str, Any],
        mp_model: int,
        *,
        correlation_id: str = "",
        source: str = "poll",
        status_text_default: str = "Unknown",
    ):
        self._apply_status_snapshot(
            status_payload,
            mp_model,
            correlation_id=correlation_id,
            source=source,
            status_text_default=status_text_default,
        )
        cache_device_status = getattr(self, "_cache_device_status", None)
        if callable(cache_device_status):
            cache_device_status(device_id, device_type, status_payload)

    async def refresh_fleet_status(self):
        async with POLLING_TELEMETRY.observe(
            "fleet::refresh",
            "FleetStateMixin.refresh_fleet_status",
            track_overlap=False,
        ):
            try:
                profiles = self._fleet_profiles()
            except Exception as exc:
                async with self:
                    self.fleet_status_summary = f"Controller profile parse failed: {exc}"
                    self.fleet_status_by_id = {}
                    self.fleet_status_cards = []
                    self.fleet_status_card_notice = "Fix controller profile JSON to populate the controller list."
                    self.fleet_map_markers = []
                    self.fleet_unmapped_device_ids = []
                    self.fleet_unmapped_profile_rows = []
                    self.fleet_map_data = []
                    self.fleet_map_layout = {}
                    self.fleet_map_figure = {}
                    self.fleet_map_src_doc = FleetService.build_map_src_doc([], self.selected_device_id)
                    self.fleet_map_notice = "Fix controller profile JSON to render the signal map."
                    self.fleet_device_rows = []
                    self.error = self.fleet_status_summary
                return

            PollingService.sync_runtime_registry(profiles)

            if not profiles:
                async with self:
                    self.fleet_status_summary = "Controller profile list is empty; using single-controller compatibility mode."
                    self.fleet_status_by_id = {}
                    self._refresh_fleet_card_fields([])
                    self._refresh_fleet_map_fields([])
                    self.fleet_device_rows = []
                    self._sync_controller_profile_rows()
                return

            selected_profile = FleetService.select_profile(profiles, self.selected_device_id)
            effective_selected_id = str(selected_profile.get("device_id", "")).strip() if selected_profile else ""

            entries: list[FleetSnapshotEntry] = []
            for profile in profiles:
                normalized = FleetService.normalize_profile(profile)
                device_id = str(normalized["device_id"])
                device_type = str(normalized.get("device_type", FleetService.DEFAULT_DEVICE_TYPE))
                config = FleetService.build_device_config(normalized)

                if bool(normalized.get("polling_enabled", True)):
                    try:
                        payload, mp_model = await PollingService.collect_snapshot(
                            device_type,
                            config,
                            device_id=device_id,
                        )
                    except Exception as exc:
                        entries.append(
                            FleetService.build_snapshot_entry(
                                device_id=device_id,
                                device_type=device_type,
                                payload=None,
                                mp_model=1,
                                error=str(exc),
                            )
                        )
                    else:
                        entries.append(
                            FleetService.build_snapshot_entry(
                                device_id=device_id,
                                device_type=device_type,
                                payload=payload,
                                mp_model=mp_model,
                            )
                        )
                    continue

                entries.append(
                    FleetService.build_snapshot_entry(
                        device_id=device_id,
                        device_type=device_type,
                        payload={
                            "is_online": False,
                            "status_text": "Polling disabled",
                            "timestamp": "",
                        },
                        mp_model=1,
                    )
                )

            refresh_view = FleetService.compile_refresh_view(entries, effective_selected_id)
            adapted = _fleet_view_to_state_fields(refresh_view)

            async with self:
                self.selected_device_id = str(adapted["selected_device_id"])
                self.fleet_status_by_id = dict(adapted["fleet_status_by_id"])
                self._refresh_fleet_card_fields(profiles)
                self.fleet_device_rows = list(adapted["fleet_device_rows"])
                self._refresh_fleet_map_fields(profiles)
                self._sync_controller_profile_rows()
                self._refresh_fleet_aggregate_fields(profiles)
                self.refresh_runtime_registry_status()

                selected_payload = adapted["selected_payload"]
                if selected_payload is not None:
                    self._apply_selected_status_result(
                        self.selected_device_id,
                        str(adapted["selected_device_type"]),
                        dict(selected_payload),
                        int(adapted["selected_mp_model"]),
                    )
                else:
                    selected_status = dict(self.fleet_status_by_id.get(self.selected_device_id, {}))
                    if selected_status:
                        self.is_online = bool(selected_status.get("is_online", False))
                        self.status_text = str(selected_status.get("status_text", "Unknown"))
                        self.last_updated = str(selected_status.get("timestamp", ""))

    @rx.event(background=True)
    async def auto_refresh_loop(self):
        """Continuously poll the fleet while live updates are enabled."""
        async with self:
            if self.auto_refresh_running:
                return
            self.auto_refresh_running = True

        try:
            while True:
                async with self:
                    refresh_enabled = self.auto_refresh_enabled
                    refresh_interval = self._refresh_interval_seconds()

                if not refresh_enabled:
                    break

                cycle_started_at = time.monotonic()
                await self.refresh_fleet_status()
                cycle_elapsed = time.monotonic() - cycle_started_at
                sleep_seconds = max(0.0, refresh_interval - cycle_elapsed)
                if sleep_seconds > 0:
                    await asyncio.sleep(sleep_seconds)
        finally:
            async with self:
                self.auto_refresh_running = False