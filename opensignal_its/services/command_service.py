"""Command orchestration services."""

from typing import Any

from ..devices.siemens_m60 import SiemensM60
from ..models.device import DeviceConfig
from .device_runtime_service import RUNTIME


class CommandService:
    """Execute controller commands and return updated state payloads."""

    @staticmethod
    async def execute_command(
        device_type: str,
        config: DeviceConfig,
        cmd_type: str,
        value: Any,
        safe_command_probe: bool,
        device_id: str = "",
    ) -> tuple[bool, dict, int, str]:
        _runtime_key, device = RUNTIME.get_or_create(device_type, config, device_id=device_id)
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

    @staticmethod
    async def execute_siemens_m60_command(
        config: DeviceConfig,
        cmd_type: str,
        value: Any,
        safe_command_probe: bool,
    ) -> tuple[bool, dict, int, str]:
        # Compatibility wrapper for existing state call sites.
        return await CommandService.execute_command(
            device_type=SiemensM60.device_type,
            config=config,
            cmd_type=cmd_type,
            value=value,
            safe_command_probe=safe_command_probe,
        )
