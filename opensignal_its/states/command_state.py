"""Command dispatch and audit state slice."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import reflex as rx

from ..db import CommandAuditRecord, STORE
from ..services import CommandSafetyService, CommandService


_COMMAND_LIFECYCLE_LABELS = {
    "awaiting_confirmation": "Awaiting Confirmation",
    "confirmation_expired": "Confirmation Expired",
    "confirmation_rejected": "Confirmation Rejected",
    "executing": "Executing",
    "applied": "Applied",
    "verified": "Verified",
    "timed_out": "Timed Out",
    "failed": "Failed",
}


class CommandStateMixin(rx.State, mixin=True):
    selected_controller_command_lifecycle: dict[str, Any] = {}
    selected_controller_command_lifecycle_notice: str = ""

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

    def _set_command_lifecycle_state(
        self,
        *,
        stage: str,
        command_id: str = "",
        correlation_id: str = "",
        device_id: str = "",
        notice: str = "",
        success: bool = False,
        is_terminal: bool = False,
        acknowledged: bool = False,
    ):
        stage_label = _COMMAND_LIFECYCLE_LABELS.get(stage, "Unknown")
        lifecycle_notice = notice.strip() or stage_label
        updated_at = self._utc_now_iso() if hasattr(self, "_utc_now_iso") else ""
        resolved_device_id = device_id.strip() or str(getattr(self, "selected_device_id", "")).strip()
        self.selected_controller_command_lifecycle = {
            "stage": stage,
            "stage_label": stage_label,
            "command_id": command_id,
            "correlation_id": correlation_id,
            "device_id": resolved_device_id,
            "notice": lifecycle_notice,
            "success": bool(success),
            "is_terminal": bool(is_terminal),
            "acknowledged": bool(acknowledged),
            "updated_at": updated_at,
        }
        self.selected_controller_command_lifecycle_notice = f"{stage_label}: {lifecycle_notice}"

    async def send_command(self, cmd_type: str, value: Any, force_confirmed: bool = False):
        """Send timing-related commands to the controller."""
        self.is_loading = True
        correlation_id = uuid4().hex
        try:
            if not self._is_role_authorized({"operator", "admin"}):
                auth_error = "Command denied: operator or admin authentication required."
                self.error = auth_error
                self._set_command_lifecycle_state(
                    stage="failed",
                    command_id=cmd_type,
                    correlation_id=correlation_id,
                    notice=auth_error,
                    success=False,
                    is_terminal=True,
                )
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
                self._start_command_confirmation(cmd_type, value, correlation_id=correlation_id)
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
                self._set_command_lifecycle_state(
                    stage="failed",
                    command_id=cmd_type,
                    correlation_id=correlation_id,
                    notice=safety.reason,
                    success=False,
                    is_terminal=True,
                )
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
            self._set_command_lifecycle_state(
                stage="executing",
                command_id=cmd_type,
                correlation_id=correlation_id,
                device_id=device_id,
                notice=f"Executing {cmd_type} for {device_id}.",
                success=False,
                is_terminal=False,
            )
            result = await CommandService.execute_command_result(
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
                success=result.success,
                error=result.error,
            )
            if result.success:
                self._apply_selected_status_result(
                    device_id,
                    device_type,
                    result.payload,
                    result.mp_model,
                    correlation_id=correlation_id,
                    source="command",
                    status_text_default="Command applied",
                )
                self._set_command_lifecycle_state(
                    stage=result.lifecycle_stage,
                    command_id=cmd_type,
                    correlation_id=correlation_id,
                    device_id=device_id,
                    notice=result.lifecycle_notice,
                    success=True,
                    is_terminal=True,
                    acknowledged=result.acknowledged,
                )
            else:
                self.m60_status = result.payload
                self.m60_status_json = json.dumps(self.m60_status, indent=2)
                self.error = result.error
                self.is_online = bool(self.m60_status.get("is_online", False))
                self._cache_device_status(device_id, device_type, self.m60_status)
                self._set_command_lifecycle_state(
                    stage=result.lifecycle_stage,
                    command_id=cmd_type,
                    correlation_id=correlation_id,
                    device_id=device_id,
                    notice=result.lifecycle_notice,
                    success=False,
                    is_terminal=True,
                    acknowledged=result.acknowledged,
                )
        except Exception as exc:
            self.error = str(exc)
            self._set_command_lifecycle_state(
                stage="failed",
                command_id=cmd_type,
                correlation_id=correlation_id,
                notice=str(exc),
                success=False,
                is_terminal=True,
            )
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