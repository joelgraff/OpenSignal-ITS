"""Minimal operator authentication helpers for command authorization."""

from __future__ import annotations

import os


class OperatorAuthService:
    """Validate operator credentials from environment configuration."""

    @staticmethod
    def required_username() -> str:
        return os.getenv("OPENSIGNAL_OPERATOR_USERNAME", "operator").strip()

    @staticmethod
    def required_password() -> str:
        return os.getenv("OPENSIGNAL_OPERATOR_PASSWORD", "").strip()

    @staticmethod
    def authenticate(username: str, password: str) -> tuple[bool, str]:
        required_password = OperatorAuthService.required_password()
        if not required_password:
            return False, "Operator login denied: OPENSIGNAL_OPERATOR_PASSWORD is not configured."

        required_username = OperatorAuthService.required_username()
        if username.strip() != required_username:
            return False, "Operator login denied: username is invalid."

        if password.strip() != required_password:
            return False, "Operator login denied: password is invalid."

        return True, "Operator login successful."
