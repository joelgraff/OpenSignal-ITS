"""Fleet status refresh and auto-refresh state slice."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import reflex as rx

from ..models.fleet import FleetRefreshView
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
    fleet_map_markers: list[dict[str, Any]] = []
    fleet_unmapped_device_ids: list[str] = []
    fleet_map_data: list[dict[str, Any]] = []
    fleet_map_layout: dict[str, Any] = {}
    fleet_map_figure: dict[str, Any] = {}
    fleet_map_notice: str = "Add controller coordinates to place signals on the map."
    fleet_online_count: int = 0
    fleet_offline_count: int = 0
    fleet_total_count: int = 0
    auto_refresh_enabled: bool = True
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
        self.fleet_status_cards = FleetService.build_profile_display_rows(
            profiles,
            self.fleet_status_by_id,
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
        unmapped = FleetService.list_unmapped_profiles(profiles)
        self.fleet_map_markers = markers
        self.fleet_unmapped_device_ids = unmapped
        self.fleet_map_data = FleetService.build_map_data(markers)
        self.fleet_map_layout = FleetService.build_map_layout(markers)
        self.fleet_map_figure = {
            "data": list(self.fleet_map_data),
            "layout": dict(self.fleet_map_layout),
        }

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

    async def refresh_fleet_status(self):
        try:
            profiles = self._fleet_profiles()
        except Exception as exc:
            self.fleet_status_summary = f"Controller profile parse failed: {exc}"
            self.fleet_status_by_id = {}
            self.fleet_status_cards = []
            self.fleet_map_markers = []
            self.fleet_unmapped_device_ids = []
            self.fleet_map_data = []
            self.fleet_map_layout = {}
            self.fleet_map_figure = {}
            self.fleet_map_notice = "Fix controller profile JSON to render the signal map."
            self.fleet_device_rows = []
            self.error = self.fleet_status_summary
            return

        if not profiles:
            self.fleet_status_summary = "Controller profile list is empty; using single-controller compatibility mode."
            self.fleet_status_by_id = {}
            self.fleet_status_cards = []
            self._refresh_fleet_map_fields([])
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
        self._refresh_fleet_card_fields(profiles)
        self.fleet_device_rows = list(adapted["fleet_device_rows"])
        self._refresh_fleet_map_fields(profiles)
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
                    except Exception as exc:
                        async with self:
                            self.m60_status = {"error": f"Unhandled exception: {exc}"}
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