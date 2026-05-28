"""Authoritative bounded command catalog for traffic-signal and first DMS paths."""

from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy
import json
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
    """Bounded command contract for the currently supported ITS commands."""

    command_id: str
    device_family: str
    device_command: str
    requires_confirmation: bool
    requires_value: bool
    value_type: str
    failure_message: str
    normalize_value: Callable[[Any], Any]
    build_execution_params: Callable[[Any, bool], dict[str, Any]]
    options: tuple[CommandOption, ...] = ()
    value_schema: dict[str, Any] | None = None
    verify_poll_payload: Callable[[Any, dict[str, Any]], tuple[bool, str]] | None = None
    verification_failure_stage: str = "failed"


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


def _normalize_optional_bool_field(
    command_id: str,
    field_name: str,
    value: Any,
    *,
    default: bool,
) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raw = str(value).strip().lower()
    if raw in _TRUE_VALUES:
        return True
    if raw in _FALSE_VALUES:
        return False
    raise ValueError(f"{command_id} {field_name} must be a boolean.")


def _normalize_no_value(_command_id: str, _value: Any) -> None:
    return None


def _normalize_set_message_value(command_id: str, value: Any) -> dict[str, Any]:
    payload = value
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            raise ValueError(f"{command_id} value must be an object.")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{command_id} value must be an object.") from exc

    if not isinstance(payload, dict):
        raise ValueError(f"{command_id} value must be an object.")

    message = str(payload.get("message", "")).strip()
    if not message:
        raise ValueError(f"{command_id} message is required.")
    if len(message) > 120:
        raise ValueError(f"{command_id} message must be 120 characters or fewer.")

    activate_plan = _normalize_optional_bool_field(
        command_id,
        "activate_plan",
        payload.get("activate_plan"),
        default=True,
    )

    return {
        "message": message,
        "activate_plan": activate_plan,
    }


def _select_pattern_params(value: int, safe_command_probe: bool) -> dict[str, Any]:
    return {
        "pattern": value,
        "probe_only": safe_command_probe,
    }


def _verify_select_pattern_payload(value: int, payload: dict[str, Any]) -> tuple[bool, str]:
    raw_data = payload.get("raw_data", {})
    if not isinstance(raw_data, dict):
        raw_data = {}

    current_pattern = str(raw_data.get("current_pattern", "")).strip()
    if current_pattern == str(int(value)):
        return True, ""

    return (
        False,
        "Post-command verification timed out: requested traffic-signal pattern did not appear after poll.",
    )


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


def _set_message_params(value: dict[str, Any], safe_command_probe: bool) -> dict[str, Any]:
    return {
        "message": value["message"],
        "activate_plan": bool(value.get("activate_plan", True)),
        "probe_only": safe_command_probe,
    }


def _verify_set_message_payload(value: dict[str, Any], payload: dict[str, Any]) -> tuple[bool, str]:
    raw_data = payload.get("raw_data", {})
    if not isinstance(raw_data, dict):
        raw_data = {}

    active_message = str(raw_data.get("active_message", "")).strip()
    message_plan_active = bool(raw_data.get("message_plan_active", False))
    expected_message = str(value.get("message", "")).strip()
    expected_activate_plan = bool(value.get("activate_plan", True))

    if active_message != expected_message:
        return False, "Post-command verification failed: requested DMS message was not present after poll."
    if message_plan_active != expected_activate_plan:
        return False, "Post-command verification failed: DMS activation state did not match the requested value."
    return True, ""


_COMMAND_CATALOG: dict[str, CommandDefinition] = {
    "select_pattern": CommandDefinition(
        command_id="select_pattern",
        device_family="traffic_signal_controller",
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
        verify_poll_payload=_verify_select_pattern_payload,
        verification_failure_stage="timed_out",
    ),
    "set_mode": CommandDefinition(
        command_id="set_mode",
        device_family="traffic_signal_controller",
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
        device_family="traffic_signal_controller",
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
        device_family="traffic_signal_controller",
        device_command="advance_phase",
        requires_confirmation=True,
        requires_value=False,
        value_type="none",
        failure_message="",
        normalize_value=lambda value: _normalize_no_value("advance_phase", value),
        build_execution_params=_advance_phase_params,
    ),
    "set_message": CommandDefinition(
        command_id="set_message",
        device_family="dynamic_message_sign",
        device_command="set_message",
        requires_confirmation=True,
        requires_value=True,
        value_type="object",
        failure_message="Failed to apply DMS message.",
        normalize_value=lambda value: _normalize_set_message_value("set_message", value),
        build_execution_params=_set_message_params,
        value_schema={
            "type": "object",
            "required": ["message"],
            "properties": {
                "message": {
                    "type": "string",
                    "min_length": 1,
                    "max_length": 120,
                },
                "activate_plan": {
                    "type": "boolean",
                },
            },
        },
        verify_poll_payload=_verify_set_message_payload,
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

    if definition.value_schema is not None:
        payload["value_schema"] = deepcopy(definition.value_schema)

    return payload


def export_command_capabilities(device_family: str | None = "traffic_signal_controller") -> list[dict[str, Any]]:
    normalized_family = None
    if device_family is not None:
        family = str(device_family).strip()
        normalized_family = family or None

    return [
        capability
        for command_id, definition in _COMMAND_CATALOG.items()
        if normalized_family is None or definition.device_family == normalized_family
        for capability in [export_command_capability(command_id)]
        if capability is not None
    ]


def command_requires_confirmation(command_id: str) -> bool:
    definition = get_command_definition(command_id)
    return bool(definition.requires_confirmation) if definition else False


def unknown_command_error(command_id: str) -> str:
    return _unknown_command_error(command_id)