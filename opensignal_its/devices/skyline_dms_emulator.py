"""Simulator-friendly first DMS target behind the device registry boundary."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .base import Device
from ..models.device import DeviceConfig, DeviceStatus
from ..services.command_catalog import export_command_capabilities


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SkylineDmsEmulator(Device):
    """Bounded Skyline-style DMS emulator for Phase 4f command validation."""

    device_type = "skyline_dms_emulator"

    def __init__(self, config: DeviceConfig):
        super().__init__(config)
        self._active_message: str = ""
        self._activate_plan: bool = True
        self._pending_message: str = ""
        self._pending_activate_plan: bool = True
        self._verification_mode: str = "confirm"
        self._last_verification_outcome: str = "idle"

    def _apply_pending_message(self) -> None:
        if not self._pending_message:
            self._last_verification_outcome = "idle"
            return

        if self._verification_mode == "message_mismatch":
            self._active_message = f"{self._pending_message} (stale)"
            self._activate_plan = self._pending_activate_plan
            self._last_verification_outcome = "mismatch"
        elif self._verification_mode == "activation_mismatch":
            self._active_message = self._pending_message
            self._activate_plan = not self._pending_activate_plan
            self._last_verification_outcome = "mismatch"
        else:
            self._active_message = self._pending_message
            self._activate_plan = self._pending_activate_plan
            self._last_verification_outcome = "verified"

        self._pending_message = ""
        self._pending_activate_plan = True

    async def connect(self) -> bool:
        self.status.timestamp = _utc_now()
        self.status.is_online = True
        self.status.status_text = "DMS emulator connected"
        self.status.errors = []
        return True

    async def poll(self) -> DeviceStatus:
        self._apply_pending_message()
        self.status.timestamp = _utc_now()
        self.status.is_online = True
        if self._last_verification_outcome == "verified":
            self.status.status_text = "Message verified"
        elif self._last_verification_outcome == "mismatch":
            self.status.status_text = "Verification mismatch"
        else:
            self.status.status_text = "Message applied" if self._active_message else "Blank message"
        self.status.raw_data = {
            "active_message": self._active_message,
            "message_plan_active": self._activate_plan,
        }
        self.status.extra = {
            "dms": {
                "target": "Skyline DMS emulator",
                "active_message": self._active_message,
                "message_plan_active": self._activate_plan,
                "verification_outcome": self._last_verification_outcome,
            }
        }
        self.status.errors = []
        return self.status

    async def command(self, command: str, params: dict[str, Any]) -> bool:
        if command != "set_message":
            self.status.timestamp = _utc_now()
            self.status.is_online = True
            self.status.status_text = "Unsupported DMS command"
            self.status.errors = [f"unsupported command {command}"]
            return False

        message = str(params.get("message", "")).strip()
        if not message:
            self.status.timestamp = _utc_now()
            self.status.is_online = True
            self.status.status_text = "Rejected empty message"
            self.status.errors = ["message is required"]
            return False

        if bool(params.get("probe_only", False)):
            self.status.timestamp = _utc_now()
            self.status.is_online = True
            self.status.status_text = "DMS probe accepted"
            self.status.errors = []
            return True

        self._pending_message = message
        self._pending_activate_plan = bool(params.get("activate_plan", True))
        self._last_verification_outcome = "accepted"
        self.status.timestamp = _utc_now()
        self.status.is_online = True
        self.status.status_text = "Message accepted"
        self.status.errors = []
        return True

    def get_capabilities(self) -> dict[str, Any]:
        return {
            "device_family": "dynamic_message_sign",
            "protocol_family": "ntcip",
            "command_capabilities": export_command_capabilities("dynamic_message_sign"),
        }