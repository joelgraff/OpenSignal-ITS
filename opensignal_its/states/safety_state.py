"""Write safety and command confirmation state slice."""

from __future__ import annotations

import json
import random
from typing import Any

from ..services import CommandSafetyService


class SafetyStateMixin:
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

    def _write_unlock_seconds(self) -> int:
        try:
            return max(15, int(self.write_unlock_seconds_text))
        except ValueError:
            return 120

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
        self.pending_confirmation_token = token
        self.pending_confirmation_expires = self._utc_future_iso(90)
        self.pending_command_type = cmd_type
        self.pending_command_value_json = json.dumps(value)
        self.pending_confirmation_notice = (
            f"Confirmation required for {cmd_type}. Enter token {token} within 90 seconds."
        )

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