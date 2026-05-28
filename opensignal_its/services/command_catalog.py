"""Authoritative catalog for the current Siemens M60 command contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


_TRUE_VALUES = {"1", "true", "yes", "on", "enable", "enabled"}
_FALSE_VALUES = {"0", "false", "no", "off", "disable", "disabled"}


@dataclass(frozen=True, slots=True)
class CommandOption:
    """JSON-safe option hint for a bounded command capability."""

    value: Any
    label: str


@dataclass(frozen=True, slots=True)
class CommandDefinition:
    """Bounded command contract for the currently supported controller commands."""

    command_id: str
    device_command: str
    requires_confirmation: bool
    requires_value: bool
    value_type: str
    failure_message: str
    normalize_value: Callable[[Any], Any]
    build_execution_params: Callable[[Any, bool], dict[str, Any]]
    options: tuple[CommandOption, ...] = ()


def _unknown_command_error(command_id: str) -> str:
    return f"Unknown command: {str(command_id).strip()}"


def _normalize_required_int(command_id: str, value: Any) -> int:
    if value is None or str(value).strip() == "":
        raise ValueError(f"{command_id} value is required.")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{command_id} value must be an integer.") from exc


def _normalize_required_string(command_id: str, value: Any) -> str:
    normalized = str(value).strip().lower()
    if not normalized:
        raise ValueError(f"{command_id} value is required.")
    return normalized


def _normalize_required_bool(command_id: str, value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        raise ValueError(f"{command_id} value must be a boolean.")
    raw = str(value).strip().lower()
    if raw in _TRUE_VALUES:
        return True
    if raw in _FALSE_VALUES:
        return False
    raise ValueError(f"{command_id} value must be a boolean.")


def _normalize_no_value(_command_id: str, _value: Any) -> None:
    return None


def _select_pattern_params(value: int, safe_command_probe: bool) -> dict[str, Any]:
    return {
        "pattern": value,
        "probe_only": safe_command_probe,
    }


def _set_mode_params(value: str, safe_command_probe: bool) -> dict[str, Any]:
    return {
        "mode": value,
        "probe_only": safe_command_probe,
    }


def _manual_hold_params(value: bool, safe_command_probe: bool) -> dict[str, Any]:
    return {
        "hold": value,
        "probe_only": safe_command_probe,
        "allow_all_phases": not safe_command_probe,
    }


def _advance_phase_params(_value: None, safe_command_probe: bool) -> dict[str, Any]:
    return {
        "probe_only": safe_command_probe,
        "allow_all_phases": not safe_command_probe,
    }


_COMMAND_CATALOG: dict[str, CommandDefinition] = {
    "select_pattern": CommandDefinition(
        command_id="select_pattern",
        device_command="select_pattern",
        requires_confirmation=True,
        requires_value=True,
        value_type="integer",
        failure_message="Failed to select pattern",
        normalize_value=lambda value: _normalize_required_int("select_pattern", value),
        build_execution_params=_select_pattern_params,
        options=(
            CommandOption(value=1, label="Pattern 1"),
            CommandOption(value=2, label="Pattern 2"),
        ),
    ),
    "set_mode": CommandDefinition(
        command_id="set_mode",
        device_command="set_mode",
        requires_confirmation=True,
        requires_value=True,
        value_type="string",
        failure_message="",
        normalize_value=lambda value: _normalize_required_string("set_mode", value),
        build_execution_params=_set_mode_params,
        options=(
            CommandOption(value="free", label="Free"),
            CommandOption(value="coordinated", label="Coord"),
        ),
    ),
    "manual_hold": CommandDefinition(
        command_id="manual_hold",
        device_command="manual_hold",
        requires_confirmation=True,
        requires_value=True,
        value_type="boolean",
        failure_message="",
        normalize_value=lambda value: _normalize_required_bool("manual_hold", value),
        build_execution_params=_manual_hold_params,
    ),
    "advance_phase": CommandDefinition(
        command_id="advance_phase",
        device_command="advance_phase",
        requires_confirmation=True,
        requires_value=False,
        value_type="none",
        failure_message="",
        normalize_value=lambda value: _normalize_no_value("advance_phase", value),
        build_execution_params=_advance_phase_params,
    ),
}


def get_command_definition(command_id: str) -> CommandDefinition | None:
    return _COMMAND_CATALOG.get(str(command_id).strip())


def export_command_capability(command_id: str) -> dict[str, Any] | None:
    definition = get_command_definition(command_id)
    if definition is None:
        return None

    payload: dict[str, Any] = {
        "command_id": definition.command_id,
        "requires_confirmation": bool(definition.requires_confirmation),
        "requires_value": bool(definition.requires_value),
        "value_type": definition.value_type,
    }

    if definition.options:
        payload["options"] = [
            {
                "value": option.value,
                "label": option.label,
            }
            for option in definition.options
        ]
        payload["allowed_values"] = [option.value for option in definition.options]
    elif definition.value_type == "boolean":
        payload["allowed_values"] = [True, False]

    return payload


def export_command_capabilities() -> list[dict[str, Any]]:
    return [
        capability
        for command_id in _COMMAND_CATALOG
        for capability in [export_command_capability(command_id)]
        if capability is not None
    ]


def command_requires_confirmation(command_id: str) -> bool:
    definition = get_command_definition(command_id)
    return bool(definition.requires_confirmation) if definition else False


def unknown_command_error(command_id: str) -> str:
    return _unknown_command_error(command_id)