"""Controller profile configuration state slice."""

from __future__ import annotations

from typing import Any

from ..services import FleetService


class ConfigurationStateMixin:
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

    def update_device_profiles_json(self, value: str):
        self.device_profiles_json = value
        self.controller_profile_form_error = ""
        self._sync_controller_profile_rows()

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