"""Controller profile configuration state slice."""

from __future__ import annotations

from typing import Any

import reflex as rx

from ..db import STORE
from ..services import FleetService, PollingService


class ConfigurationStateMixin(rx.State, mixin=True):
    CONTROLLER_PROFILE_SETTINGS_KEY: str = "controller_profiles_json"
    device_profiles_json: str = "[]"
    controller_profile_rows: list[dict[str, Any]] = []
    controller_profile_notice: str = "No controller profiles configured yet."
    controller_profile_filter_text: str = ""
    controller_profile_mapping_filter: str = "all"
    controller_profile_sort_key: str = "device_id"
    controller_profile_sort_desc: bool = False
    controller_profile_form_error: str = ""
    controller_profile_original_device_id: str = ""
    controller_profile_form_device_id: str = ""
    controller_profile_form_name: str = ""
    controller_profile_form_location_name: str = ""
    controller_profile_form_device_type: str = FleetService.DEFAULT_DEVICE_TYPE
    controller_profile_form_ip_address: str = ""
    controller_profile_form_port_text: str = "161"
    controller_profile_form_community: str = "public"
    controller_profile_form_snmp_version: str = "auto"
    controller_profile_form_timeout_text: str = "3"
    controller_profile_form_retries_text: str = "1"
    controller_profile_form_polling_enabled: bool = True
    controller_profile_form_latitude_text: str = ""
    controller_profile_form_longitude_text: str = ""
    controller_profile_map_point_latitude_text: str = ""
    controller_profile_map_point_longitude_text: str = ""
    controller_profile_creation_dialog_open: bool = False

    def update_device_profiles_json(self, value: str):
        self.device_profiles_json = value
        self.controller_profile_form_error = ""
        self._sync_controller_profile_rows()
        self._persist_controller_profiles_json()
        refresh_cards = getattr(self, "_refresh_fleet_card_fields", None)
        if callable(refresh_cards):
            refresh_cards()
        refresh_map = getattr(self, "_refresh_fleet_map_fields", None)
        if callable(refresh_map):
            refresh_map()

    def _persist_controller_profiles_json(self):
        try:
            STORE.set_app_setting(self.CONTROLLER_PROFILE_SETTINGS_KEY, self.device_profiles_json)
        except Exception:
            pass

    def initialize_controller_profiles(self):
        try:
            persisted = STORE.get_app_setting(self.CONTROLLER_PROFILE_SETTINGS_KEY, "").strip()
        except Exception:
            persisted = ""

        if persisted:
            self.device_profiles_json = persisted

        profiles = self._sync_controller_profile_rows()
        refresh_cards = getattr(self, "_refresh_fleet_card_fields", None)
        if callable(refresh_cards):
            refresh_cards(profiles)
        refresh_map = getattr(self, "_refresh_fleet_map_fields", None)
        if callable(refresh_map):
            refresh_map(profiles)

        if not self.controller_profile_notice.startswith("Profile JSON error:"):
            PollingService.sync_runtime_registry(profiles)
            refresh_runtime_registry = getattr(self, "refresh_runtime_registry_status", None)
            if callable(refresh_runtime_registry):
                refresh_runtime_registry()

        selected_hint = (
            str(getattr(self, "selected_device_id", "")).strip()
            or str(getattr(self, "controller_profile_original_device_id", "")).strip()
            or str(getattr(self, "controller_profile_form_device_id", "")).strip()
        )
        selected_profile = FleetService.select_profile(profiles, selected_hint)
        selected_device_id = str(selected_profile.get("device_id", "")).strip() if selected_profile else ""
        load_profile = getattr(self, "load_controller_profile", None)
        if selected_device_id and callable(load_profile):
            load_profile(selected_device_id)

        if hasattr(self, "auto_refresh_running"):
            self.auto_refresh_running = False

        auto_refresh_handler = getattr(type(self), "auto_refresh_loop", None)
        if callable(auto_refresh_handler) and getattr(auto_refresh_handler, "is_background", False):
            return auto_refresh_handler()

    def update_controller_profile_filter_text(self, value: str):
        self.controller_profile_filter_text = value
        self._sync_controller_profile_rows()

    def update_controller_profile_mapping_filter(self, value: str):
        normalized = value.strip().lower()
        if normalized not in {"all", "mapped", "unmapped"}:
            return
        self.controller_profile_mapping_filter = normalized
        self._sync_controller_profile_rows()

    def update_controller_profile_sort_key(self, value: str):
        normalized = value.strip().lower()
        if normalized not in {"device_id", "name", "location_name", "ip_address"}:
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

    def update_controller_profile_form_location_name(self, value: str):
        self.controller_profile_form_location_name = value

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

    def update_controller_profile_form_polling_enabled(self, value: bool):
        self.controller_profile_form_polling_enabled = bool(value)

    def update_controller_profile_form_latitude_text(self, value: str):
        self.controller_profile_form_latitude_text = value

    def update_controller_profile_form_longitude_text(self, value: str):
        self.controller_profile_form_longitude_text = value

    def _set_controller_profile_map_point(self, latitude: float, longitude: float):
        self.controller_profile_map_point_latitude_text = (
            f"{float(latitude):.6f}".rstrip("0").rstrip(".")
        )
        self.controller_profile_map_point_longitude_text = (
            f"{float(longitude):.6f}".rstrip("0").rstrip(".")
        )
        if self.controller_profile_creation_dialog_open:
            self.controller_profile_form_latitude_text = self.controller_profile_map_point_latitude_text
            self.controller_profile_form_longitude_text = self.controller_profile_map_point_longitude_text

    def select_controller_profile_map_point(self, latitude: float, longitude: float):
        self._set_controller_profile_map_point(latitude, longitude)
        self.controller_profile_form_error = ""
        self.controller_profile_notice = "Selected a map point. Click Add to open the controller dialog."

    def set_controller_profile_creation_dialog_open(self, value: bool):
        self.controller_profile_creation_dialog_open = bool(value)

    def open_controller_profile_creation_dialog(self):
        self._reset_controller_profile_form()
        self.controller_profile_form_latitude_text = self.controller_profile_map_point_latitude_text
        self.controller_profile_form_longitude_text = self.controller_profile_map_point_longitude_text
        self.controller_profile_creation_dialog_open = True
        if self.controller_profile_form_latitude_text and self.controller_profile_form_longitude_text:
            self.controller_profile_notice = "Create a controller at the selected map point."
        else:
            self.controller_profile_notice = "Click the map to choose a point, then click Add."

    def _reset_controller_profile_form(self):
        self.controller_profile_form_error = ""
        self.controller_profile_original_device_id = ""
        self.controller_profile_form_device_id = ""
        self.controller_profile_form_name = ""
        self.controller_profile_form_location_name = ""
        self.controller_profile_form_device_type = FleetService.DEFAULT_DEVICE_TYPE
        self.controller_profile_form_ip_address = ""
        self.controller_profile_form_port_text = "161"
        self.controller_profile_form_community = "public"
        self.controller_profile_form_snmp_version = "auto"
        self.controller_profile_form_timeout_text = "3"
        self.controller_profile_form_retries_text = "1"
        self.controller_profile_form_polling_enabled = True
        self.controller_profile_form_latitude_text = ""
        self.controller_profile_form_longitude_text = ""

    def close_controller_profile_creation_dialog(self):
        self.controller_profile_creation_dialog_open = False

    def _sync_controller_profile_rows(self, notice: str = "") -> list[dict[str, Any]]:
        try:
            profiles = FleetService.parse_profiles_json(self.device_profiles_json)
        except Exception as exc:
            self.controller_profile_rows = []
            self.controller_profile_notice = f"Profile JSON error: {exc}"
            return []

        filtered_profiles = FleetService.filter_profiles(profiles, self.controller_profile_filter_text)
        visible_profiles = FleetService.filter_profiles_by_mapping(
            filtered_profiles,
            self.controller_profile_mapping_filter,
        )
        ordered_profiles = FleetService.sort_profiles(
            visible_profiles,
            self.controller_profile_sort_key,
            self.controller_profile_sort_desc,
        )
        self.controller_profile_rows = FleetService.build_profile_display_rows(
            ordered_profiles,
            self.fleet_status_by_id,
        )
        summary_suffix = ""
        query = self.controller_profile_filter_text.strip()
        has_active_filters = bool(query) or self.controller_profile_mapping_filter != "all"
        if has_active_filters and profiles:
            summary_suffix = f" Showing {len(visible_profiles)} of {len(profiles)} controller profiles."

        if notice:
            self.controller_profile_notice = notice + summary_suffix
        elif not profiles:
            self.controller_profile_notice = "No controller profiles configured yet."
        elif has_active_filters and not visible_profiles:
            self.controller_profile_notice = "No controller profiles match the current filters."
        else:
            suffix = "" if len(profiles) == 1 else "s"
            self.controller_profile_notice = f"{len(profiles)} controller profile{suffix} configured.{summary_suffix}"
        return profiles

    def new_controller_profile(self):
        self.controller_profile_map_point_latitude_text = ""
        self.controller_profile_map_point_longitude_text = ""
        self._reset_controller_profile_form()
        self.controller_profile_creation_dialog_open = False
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
        self.controller_profile_form_location_name = str(selected.get("location_name", "")).strip()
        self.controller_profile_form_device_type = str(
            selected.get("device_type", FleetService.DEFAULT_DEVICE_TYPE)
        ).strip() or FleetService.DEFAULT_DEVICE_TYPE
        self.controller_profile_form_ip_address = str(selected.get("ip_address", "")).strip()
        self.controller_profile_form_port_text = str(selected.get("port", 161)).strip()
        self.controller_profile_form_community = str(selected.get("community", "public")).strip()
        self.controller_profile_form_snmp_version = str(selected.get("snmp_version", "auto")).strip()
        self.controller_profile_form_timeout_text = str(selected.get("timeout_seconds", 3.0)).strip()
        self.controller_profile_form_retries_text = str(selected.get("retries", 1)).strip()
        self.controller_profile_form_latitude_text = (
            "" if selected.get("latitude") is None else str(selected.get("latitude", ""))
        )
        self.controller_profile_form_longitude_text = (
            "" if selected.get("longitude") is None else str(selected.get("longitude", ""))
        )
        self.controller_profile_form_polling_enabled = bool(selected.get("polling_enabled", True))
        if hasattr(self, "managed_polling_notice"):
            self.managed_polling_notice = (
                f"Active polling is {'enabled' if self.controller_profile_form_polling_enabled else 'paused'} for {target}."
            )
        self.selected_device_id = self.controller_profile_form_device_id
        self.controller_profile_notice = f"Loaded controller profile {target}."
        self.controller_profile_form_error = ""
        self.controller_profile_creation_dialog_open = False
        refresh_map = getattr(self, "_refresh_fleet_map_fields", None)
        if callable(refresh_map):
            refresh_map()

    def load_controller_profile_from_row(self, device_id: str):
        self.load_controller_profile(device_id)

    def open_controller_profile_editor(self, device_id: str):
        target = device_id.strip()
        if not target:
            self.controller_profile_notice = "Choose a controller profile to edit."
            return

        self.controller_profile_filter_text = ""
        self.controller_profile_mapping_filter = "all"

        update_workspace_mode = getattr(self, "update_ui_workspace_mode", None)
        if callable(update_workspace_mode):
            update_workspace_mode("configuration")
        else:
            self.ui_workspace_mode = "configuration"
            self._sync_controller_profile_rows()

        self.load_controller_profile(target)
        if self.controller_profile_original_device_id == target:
            self.controller_profile_notice = (
                f"Opened Controllers for {target}. Add coordinates and save to place it on the map."
            )

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
            existing_profile = None
            existing_lookup_id = original_device_id or target_device_id
            if existing_lookup_id:
                existing_profile = FleetService.select_profile(profiles, existing_lookup_id)
            if original_device_id and original_device_id != target_device_id:
                updated_profiles = FleetService.remove_profile(updated_profiles, original_device_id)
            profile = FleetService.build_profile_from_form(
                device_id=target_device_id,
                name=self.controller_profile_form_name,
                location_name=self.controller_profile_form_location_name,
                device_type=self.controller_profile_form_device_type,
                ip_address_text=self.controller_profile_form_ip_address,
                port_text=self.controller_profile_form_port_text,
                community=self.controller_profile_form_community,
                snmp_version=self.controller_profile_form_snmp_version,
                timeout_text=self.controller_profile_form_timeout_text,
                retries_text=self.controller_profile_form_retries_text,
                latitude_text=self.controller_profile_form_latitude_text,
                longitude_text=self.controller_profile_form_longitude_text,
                polling_enabled=self.controller_profile_form_polling_enabled,
            )
            if existing_profile is not None and not profile.get("media_streams"):
                profile["media_streams"] = list(existing_profile.get("media_streams", []))
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
        self.controller_profile_map_point_latitude_text = ""
        self.controller_profile_map_point_longitude_text = ""
        self.controller_profile_creation_dialog_open = False
        self._persist_controller_profiles_json()
        self._sync_controller_profile_rows(f"Saved controller profile {target_device_id}.")
        refresh_cards = getattr(self, "_refresh_fleet_card_fields", None)
        if callable(refresh_cards):
            refresh_cards(updated_profiles)
        refresh_map = getattr(self, "_refresh_fleet_map_fields", None)
        if callable(refresh_map):
            refresh_map(updated_profiles)
        PollingService.sync_runtime_registry(updated_profiles)
        refresh_runtime_registry = getattr(self, "refresh_runtime_registry_status", None)
        if callable(refresh_runtime_registry):
            refresh_runtime_registry()
        return rx.remove_local_storage(FleetService.MAP_CREATE_STORAGE_KEY)

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
        self.controller_profile_creation_dialog_open = False
        self._persist_controller_profiles_json()
        self._sync_controller_profile_rows(f"Removed controller profile {target}.")
        refresh_cards = getattr(self, "_refresh_fleet_card_fields", None)
        if callable(refresh_cards):
            refresh_cards(updated_profiles)
        refresh_map = getattr(self, "_refresh_fleet_map_fields", None)
        if callable(refresh_map):
            refresh_map(updated_profiles)
        PollingService.sync_runtime_registry(updated_profiles)
        refresh_runtime_registry = getattr(self, "refresh_runtime_registry_status", None)
        if callable(refresh_runtime_registry):
            refresh_runtime_registry()

    def update_controller_profile_polling_enabled(self, value: bool):
        self.controller_profile_form_error = ""
        target = self.controller_profile_original_device_id.strip() or self.selected_device_id.strip()
        if not target:
            self.controller_profile_notice = "Choose a controller profile before changing polling."
            return

        try:
            profiles = FleetService.parse_profiles_json(self.device_profiles_json)
        except Exception as exc:
            self.controller_profile_form_error = str(exc)
            self.controller_profile_notice = f"Cannot update polling state: {exc}"
            return

        polling_enabled = bool(value)
        updated_profiles: list[dict[str, Any]] = []
        found = False
        for profile in profiles:
            normalized = dict(profile)
            if str(normalized.get("device_id", "")).strip() == target:
                normalized["polling_enabled"] = polling_enabled
                found = True
            updated_profiles.append(normalized)

        if not found:
            self.controller_profile_notice = f"Controller profile {target} was not found."
            return

        self.controller_profile_form_polling_enabled = polling_enabled
        if hasattr(self, "managed_polling_notice"):
            self.managed_polling_notice = (
                f"Active polling is {'enabled' if polling_enabled else 'paused'} for {target}."
            )
        self.device_profiles_json = FleetService.dump_profiles_json(updated_profiles)
        self._persist_controller_profiles_json()
        self._sync_controller_profile_rows(
            f"Polling {'enabled' if polling_enabled else 'disabled'} for {target}."
        )
        refresh_cards = getattr(self, "_refresh_fleet_card_fields", None)
        if callable(refresh_cards):
            refresh_cards(updated_profiles)
        refresh_map = getattr(self, "_refresh_fleet_map_fields", None)
        if callable(refresh_map):
            refresh_map(updated_profiles)
        PollingService.sync_runtime_registry(updated_profiles)
        refresh_runtime_registry = getattr(self, "refresh_runtime_registry_status", None)
        if callable(refresh_runtime_registry):
            refresh_runtime_registry()

        refresh_fleet_status = getattr(type(self), "refresh_fleet_status", None)
        if callable(refresh_fleet_status):
            return refresh_fleet_status()
    def open_selected_controller_status(self):
        target = self.controller_profile_form_device_id.strip() or self.controller_profile_original_device_id.strip()
        if not target:
            self.controller_profile_notice = "Save or load a controller profile before opening Overview."
            return

        self.selected_device_id = target
        self.ui_workspace_mode = "monitor"
        self.monitor_view = "intersection"
        self.controller_profile_creation_dialog_open = False
        self.controller_profile_notice = f"Opened Overview for {target}."
        refresh_map = getattr(self, "_refresh_fleet_map_fields", None)
        if callable(refresh_map):
            refresh_map()