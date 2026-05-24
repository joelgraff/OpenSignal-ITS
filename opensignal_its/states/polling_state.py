"""Managed polling and runtime registry state slice."""

from __future__ import annotations

from typing import Any

from ..models.fleet import RuntimeRegistryView
from ..services import FleetService, PollingService


def _runtime_registry_view_to_state_fields(view: RuntimeRegistryView) -> dict[str, Any]:
    return {
        "runtime_registry_summary": str(view.summary),
        "runtime_registry_rows": list(view.rows),
    }


class PollingStateMixin:
    managed_polling_interval_text: str = "5"
    managed_polling_notice: str = "Controller polling idle."
    runtime_registry_summary: str = "Active poll sessions idle."
    runtime_registry_rows: list[str] = []

    def update_managed_polling_interval_text(self, value: str):
        self.managed_polling_interval_text = value

    def _managed_polling_interval_seconds(self) -> int:
        try:
            return max(1, int(self.managed_polling_interval_text))
        except ValueError:
            return 5

    def refresh_runtime_registry_status(self):
        status = PollingService.runtime_status()
        view = FleetService.build_runtime_registry_view(status)
        adapted = _runtime_registry_view_to_state_fields(view)
        self.runtime_registry_summary = adapted["runtime_registry_summary"]
        self.runtime_registry_rows = adapted["runtime_registry_rows"]

    async def start_selected_managed_polling(self):
        device_type, device_id, config = self._selected_device_target()
        ok, message = await PollingService.start_managed_polling(
            device_type=device_type,
            config=config,
            device_id=device_id,
            interval_seconds=self._managed_polling_interval_seconds(),
        )
        self.managed_polling_notice = message
        self.error = "" if ok else message
        self.refresh_runtime_registry_status()

    async def start_fleet_managed_polling(self):
        if not self._is_role_authorized({"admin"}):
            self.managed_polling_notice = "Controller polling start denied: admin authentication required."
            self.error = self.managed_polling_notice
            return

        try:
            profiles = self._fleet_profiles()
        except Exception as exc:
            self.managed_polling_notice = f"Controller profile parse failed: {exc}"
            self.error = self.managed_polling_notice
            return

        if not profiles:
            self.managed_polling_notice = "Controller polling start skipped: no configured controller profiles."
            self.error = ""
            return

        started = 0
        failed = 0
        for profile in profiles:
            device_id = str(profile.get("device_id", "unknown"))
            device_type = str(profile.get("device_type", FleetService.DEFAULT_DEVICE_TYPE))
            config = FleetService.build_device_config(profile)
            ok, _ = await PollingService.start_managed_polling(
                device_type=device_type,
                config=config,
                device_id=device_id,
                interval_seconds=self._managed_polling_interval_seconds(),
            )
            if ok:
                started += 1
            else:
                failed += 1

        self.managed_polling_notice = f"Controller polling start complete: {started} succeeded, {failed} failed."
        self.error = "" if failed == 0 else self.managed_polling_notice
        self.refresh_runtime_registry_status()

    def stop_selected_managed_polling(self):
        device_type, device_id, config = self._selected_device_target()
        ok, message = PollingService.stop_managed_polling(
            device_type=device_type,
            config=config,
            device_id=device_id,
        )
        self.managed_polling_notice = message
        self.error = "" if ok else message
        self.refresh_runtime_registry_status()

    def stop_fleet_managed_polling(self):
        if not self._is_role_authorized({"admin"}):
            self.managed_polling_notice = "Controller polling stop denied: admin authentication required."
            self.error = self.managed_polling_notice
            return

        try:
            profiles = self._fleet_profiles()
        except Exception as exc:
            self.managed_polling_notice = f"Controller profile parse failed: {exc}"
            self.error = self.managed_polling_notice
            return

        if not profiles:
            self.managed_polling_notice = "Controller polling stop skipped: no configured controller profiles."
            self.error = ""
            return

        stopped = 0
        missing = 0
        for profile in profiles:
            device_id = str(profile.get("device_id", "unknown"))
            device_type = str(profile.get("device_type", FleetService.DEFAULT_DEVICE_TYPE))
            config = FleetService.build_device_config(profile)
            ok, _ = PollingService.stop_managed_polling(
                device_type=device_type,
                config=config,
                device_id=device_id,
            )
            if ok:
                stopped += 1
            else:
                missing += 1

        self.managed_polling_notice = f"Site polling stop complete: {stopped} stopped, {missing} not running."
        self.error = ""
        self.refresh_runtime_registry_status()