"""Runtime safety preflight checks and startup bootstrap helpers."""

from __future__ import annotations

import os

from ..db import STORE
from .secret_service import parse_secret_values


def _is_production_like() -> bool:
    env = os.getenv("OPENSIGNAL_ENV", "dev").strip().lower()
    return env in {"prod", "production", "staging", "pilot"}


def _parse_positive_int(env_name: str, default: int) -> int:
    raw = os.getenv(env_name, str(default)).strip()
    try:
        parsed = int(raw)
    except ValueError as exc:
        raise ValueError(f"{env_name} must be an integer, got: {raw!r}") from exc
    if parsed <= 0:
        raise ValueError(f"{env_name} must be > 0, got: {parsed}")
    return parsed


def _has_any_secret(*env_names: str) -> bool:
    for env_name in env_names:
        if os.getenv(env_name, "").strip():
            return True
    return False


def _plain_secret_too_short(env_name: str, minimum: int = 12) -> bool:
    values = parse_secret_values(os.getenv(env_name, ""))
    if not values:
        return False
    return any(len(value) < minimum for value in values)


def validate_runtime_configuration() -> list[str]:
    """Return a list of blocking configuration errors."""
    errors: list[str] = []

    if _is_production_like():
        if not _has_any_secret(
            "OPENSIGNAL_OPERATOR_PASSWORD",
            "OPENSIGNAL_OPERATOR_PASSWORD_HASH",
            "OPENSIGNAL_OPERATOR_PASSWORD_HASHES",
        ):
            errors.append("OPENSIGNAL_OPERATOR_PASSWORD is required in production-like environments.")
        if not _has_any_secret(
            "OPENSIGNAL_OPERATOR_KEY",
            "OPENSIGNAL_OPERATOR_KEY_HASH",
            "OPENSIGNAL_OPERATOR_KEY_HASHES",
        ):
            errors.append("OPENSIGNAL_OPERATOR_KEY is required in production-like environments.")
        if not _has_any_secret(
            "OPENSIGNAL_ADMIN_PASSWORD",
            "OPENSIGNAL_ADMIN_PASSWORD_HASH",
            "OPENSIGNAL_ADMIN_PASSWORD_HASHES",
        ):
            errors.append("OPENSIGNAL_ADMIN_PASSWORD is required in production-like environments.")
        if not _has_any_secret(
            "OPENSIGNAL_ADMIN_RECOVERY_KEY",
            "OPENSIGNAL_ADMIN_RECOVERY_KEY_HASH",
            "OPENSIGNAL_ADMIN_RECOVERY_KEY_HASHES",
        ):
            errors.append("OPENSIGNAL_ADMIN_RECOVERY_KEY is required in production-like environments.")

        if _plain_secret_too_short("OPENSIGNAL_OPERATOR_PASSWORD"):
            errors.append("OPENSIGNAL_OPERATOR_PASSWORD must be at least 12 chars when using plaintext values.")
        if _plain_secret_too_short("OPENSIGNAL_OPERATOR_KEY"):
            errors.append("OPENSIGNAL_OPERATOR_KEY must be at least 12 chars when using plaintext values.")
        if _plain_secret_too_short("OPENSIGNAL_ADMIN_PASSWORD"):
            errors.append("OPENSIGNAL_ADMIN_PASSWORD must be at least 12 chars when using plaintext values.")
        if _plain_secret_too_short("OPENSIGNAL_ADMIN_RECOVERY_KEY"):
            errors.append("OPENSIGNAL_ADMIN_RECOVERY_KEY must be at least 12 chars when using plaintext values.")

    for env_name, default in (
        ("OPENSIGNAL_COMMAND_RETENTION_DAYS", 90),
        ("OPENSIGNAL_SNAPSHOT_RETENTION_DAYS", 30),
    ):
        try:
            _parse_positive_int(env_name, default)
        except ValueError as exc:
            errors.append(str(exc))

    scheduler_enabled = os.getenv("OPENSIGNAL_ENABLE_RETENTION_SCHEDULER", "false").strip().lower()
    if scheduler_enabled in {"1", "true", "yes", "on"}:
        try:
            interval = _parse_positive_int("OPENSIGNAL_RETENTION_SCHEDULE_SECONDS", 3600)
            if interval < 300:
                errors.append("OPENSIGNAL_RETENTION_SCHEDULE_SECONDS must be >= 300")
        except ValueError as exc:
            errors.append(str(exc))

    return errors


def bootstrap_runtime_safety() -> None:
    """Validate configuration and optionally apply retention cleanup."""
    errors = validate_runtime_configuration()
    if errors:
        raise RuntimeError("Runtime preflight failed: " + " | ".join(errors))

    apply_retention = os.getenv("OPENSIGNAL_APPLY_RETENTION_ON_START", "true").strip().lower()
    if apply_retention in {"1", "true", "yes", "on"}:
        STORE.apply_retention_from_env()
