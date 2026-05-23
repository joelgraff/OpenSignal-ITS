"""Minimal operator authentication helpers for command authorization."""

from __future__ import annotations

import os

from .secret_service import any_secret_matches, parse_secret_values


class OperatorAuthService:
    """Validate operator credentials from environment configuration."""

    ROLE_VIEWER = "viewer"
    ROLE_OPERATOR = "operator"
    ROLE_ADMIN = "admin"

    @staticmethod
    def required_operator_username() -> str:
        return os.getenv("OPENSIGNAL_OPERATOR_USERNAME", "operator").strip()

    @staticmethod
    def required_admin_username() -> str:
        return os.getenv("OPENSIGNAL_ADMIN_USERNAME", "admin").strip()

    @staticmethod
    def _configured_values(single_key: str, hash_key: str, hashes_key: str) -> list[str]:
        values: list[str] = []
        if os.getenv(single_key, "").strip():
            values.extend(parse_secret_values(os.getenv(single_key, "")))
        if os.getenv(hash_key, "").strip():
            values.extend(parse_secret_values(os.getenv(hash_key, "")))
        if os.getenv(hashes_key, "").strip():
            values.extend(parse_secret_values(os.getenv(hashes_key, "")))
        return values

    @staticmethod
    def required_operator_password_values() -> list[str]:
        return OperatorAuthService._configured_values(
            "OPENSIGNAL_OPERATOR_PASSWORD",
            "OPENSIGNAL_OPERATOR_PASSWORD_HASH",
            "OPENSIGNAL_OPERATOR_PASSWORD_HASHES",
        )

    @staticmethod
    def required_admin_password_values() -> list[str]:
        return OperatorAuthService._configured_values(
            "OPENSIGNAL_ADMIN_PASSWORD",
            "OPENSIGNAL_ADMIN_PASSWORD_HASH",
            "OPENSIGNAL_ADMIN_PASSWORD_HASHES",
        )

    @staticmethod
    def required_admin_recovery_key_values() -> list[str]:
        return OperatorAuthService._configured_values(
            "OPENSIGNAL_ADMIN_RECOVERY_KEY",
            "OPENSIGNAL_ADMIN_RECOVERY_KEY_HASH",
            "OPENSIGNAL_ADMIN_RECOVERY_KEY_HASHES",
        )

    @staticmethod
    def _authenticate_operator(username: str, password: str) -> tuple[bool, str, str]:
        required_password_values = OperatorAuthService.required_operator_password_values()
        if not required_password_values:
            return (
                False,
                "Operator login denied: OPENSIGNAL_OPERATOR_PASSWORD is not configured.",
                OperatorAuthService.ROLE_VIEWER,
            )

        required_username = OperatorAuthService.required_operator_username()
        if username.strip() != required_username:
            return False, "Operator login denied: username is invalid.", OperatorAuthService.ROLE_VIEWER

        if not any_secret_matches(password, required_password_values):
            return False, "Operator login denied: password is invalid.", OperatorAuthService.ROLE_VIEWER

        return True, "Operator login successful.", OperatorAuthService.ROLE_OPERATOR

    @staticmethod
    def _authenticate_admin(username: str, password: str) -> tuple[bool, str, str]:
        required_password_values = OperatorAuthService.required_admin_password_values()
        if not required_password_values:
            return False, "Admin login denied: OPENSIGNAL_ADMIN_PASSWORD is not configured.", OperatorAuthService.ROLE_VIEWER

        required_username = OperatorAuthService.required_admin_username()
        if username.strip() != required_username:
            return False, "Admin login denied: username is invalid.", OperatorAuthService.ROLE_VIEWER

        if not any_secret_matches(password, required_password_values):
            return False, "Admin login denied: password is invalid.", OperatorAuthService.ROLE_VIEWER

        return True, "Admin login successful.", OperatorAuthService.ROLE_ADMIN

    @staticmethod
    def authenticate_with_role(username: str, password: str) -> tuple[bool, str, str]:
        admin_name = OperatorAuthService.required_admin_username()
        if username.strip() == admin_name and OperatorAuthService.required_admin_password_values():
            return OperatorAuthService._authenticate_admin(username, password)
        return OperatorAuthService._authenticate_operator(username, password)

    @staticmethod
    def authenticate(username: str, password: str) -> tuple[bool, str]:
        success, message, _role = OperatorAuthService.authenticate_with_role(username, password)
        return success, message

    @staticmethod
    def role_authorized(current_role: str, allowed_roles: set[str]) -> bool:
        return current_role in allowed_roles

    @staticmethod
    def validate_admin_recovery_key(recovery_key_input: str) -> tuple[bool, str]:
        configured = OperatorAuthService.required_admin_recovery_key_values()
        if not configured:
            return False, "Recovery denied: OPENSIGNAL_ADMIN_RECOVERY_KEY is not configured."
        if not any_secret_matches(recovery_key_input, configured):
            return False, "Recovery denied: admin recovery key is invalid."
        return True, "Recovery key accepted."
