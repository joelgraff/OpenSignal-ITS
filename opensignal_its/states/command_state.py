"""Command dispatch and audit state slice."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from ..db import CommandAuditRecord, STORE
from ..services import CommandSafetyService, CommandService


class CommandStateMixin:
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
                    timestamp=self._utc_now_iso(),
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
        except Exception as exc:
            self.error = str(exc)
        finally:
            self.is_loading = False

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