"""Command orchestration services."""

from typing import Any

from ..devices.siemens_m60 import SiemensM60
from ..models.device import DeviceConfig
from .command_catalog import get_command_definition, unknown_command_error
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
        mp_model = getattr(device, "_mp_model", 1)
        definition = get_command_definition(cmd_type)
        if definition is None:
            payload = device.status.model_dump(mode="json")
            return False, payload, mp_model, unknown_command_error(cmd_type)

        try:
            normalized_value = definition.normalize_value(value)
            execution_params = definition.build_execution_params(normalized_value, safe_command_probe)
        except ValueError as exc:
            payload = device.status.model_dump(mode="json")
            return False, payload, mp_model, str(exc)

        if not await device.connect():
            payload = device.status.model_dump(mode="json")
            return False, payload, mp_model, "Controller connection failed before command"

        success = await device.command(definition.device_command, execution_params)
        error = "" if success else definition.failure_message

        if success:
            payload = (await device.poll()).model_dump(mode="json")
        else:
            payload = device.status.model_dump(mode="json")
            if not error:
                error = f"Command failed: {cmd_type}"

        return success, payload, getattr(device, "_mp_model", mp_model), error

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
