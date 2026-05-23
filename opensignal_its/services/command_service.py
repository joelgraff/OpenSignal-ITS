"""Command orchestration services."""

from typing import Any

from ..devices.siemens_m60 import SiemensM60
from ..models.device import DeviceConfig


class CommandService:
    """Execute controller commands and return updated state payloads."""

    @staticmethod
    async def execute_siemens_m60_command(
        config: DeviceConfig,
        cmd_type: str,
        value: Any,
        safe_command_probe: bool,
    ) -> tuple[bool, dict, int, str]:
        device = SiemensM60(config)
        if not await device.connect():
            payload = device.status.model_dump(mode="json")
            return False, payload, getattr(device, "_mp_model", 1), "Controller connection failed before command"

        success = False
        error = ""
        if cmd_type == "select_pattern":
            success = await device.command(
                "select_pattern",
                {"pattern": value, "probe_only": safe_command_probe},
            )
            error = "" if success else "Failed to select pattern"
        elif cmd_type == "set_mode":
            success = await device.command(
                "set_mode",
                {"mode": value, "probe_only": safe_command_probe},
            )
        elif cmd_type == "manual_hold":
            success = await device.command(
                "manual_hold",
                {"hold": value, "probe_only": safe_command_probe},
            )
        elif cmd_type == "advance_phase":
            success = await device.command(
                "advance_phase",
                {"probe_only": safe_command_probe},
            )
        else:
            error = f"Unknown command: {cmd_type}"

        if success:
            payload = (await device.poll()).model_dump(mode="json")
        else:
            payload = device.status.model_dump(mode="json")
            if not error:
                error = f"Command failed: {cmd_type}"

        return success, payload, getattr(device, "_mp_model", 1), error
