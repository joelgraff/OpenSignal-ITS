"""Operational safety policy checks for controller commands."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


def _parse_iso(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class SafetyDecision:
    allowed: bool
    reason: str


class CommandSafetyService:
    """Central policy checks for whether command execution is allowed."""

    @staticmethod
    def required_operator_key() -> str:
        return os.getenv("OPENSIGNAL_OPERATOR_KEY", "").strip()

    @staticmethod
    def unlock_write_mode(
        operator_key_input: str,
        requested_seconds: int,
    ) -> tuple[bool, str, str]:
        required = CommandSafetyService.required_operator_key()
        if not required:
            return (
                False,
                "Write unlock denied: OPENSIGNAL_OPERATOR_KEY is not configured.",
                "",
            )
        if operator_key_input.strip() != required:
            return False, "Write unlock denied: operator key is invalid.", ""

        bounded_seconds = max(15, min(900, requested_seconds))
        until = _now_utc() + timedelta(seconds=bounded_seconds)
        return True, f"Write mode unlocked for {bounded_seconds} seconds.", until.isoformat()

    @staticmethod
    def evaluate_command(
        safe_command_probe: bool,
        write_unlock_until: str,
    ) -> SafetyDecision:
        if safe_command_probe:
            return SafetyDecision(True, "Probe mode enabled (read-only command validation).")

        expiry = _parse_iso(write_unlock_until)
        if expiry is None:
            return SafetyDecision(False, "Write command denied: write mode is not unlocked.")

        if _now_utc() >= expiry:
            return SafetyDecision(False, "Write command denied: write unlock expired.")

        return SafetyDecision(True, "Write command allowed: unlock window active.")
