"""Authentication and operator recovery state slice."""

from __future__ import annotations

import os

from ..services import OperatorAuthService


_LOGIN_DISABLED = os.getenv("OPENSIGNAL_DISABLE_LOGIN", "1").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
_LOGIN_BYPASS_OPERATOR = os.getenv("OPENSIGNAL_BYPASS_OPERATOR", "local-access").strip() or "local-access"


class AuthStateMixin:
    login_username_input: str = ""
    login_password_input: str = ""
    is_authenticated: bool = _LOGIN_DISABLED
    current_operator: str = _LOGIN_BYPASS_OPERATOR if _LOGIN_DISABLED else ""
    current_role: str = "admin" if _LOGIN_DISABLED else "viewer"
    auth_notice: str = (
        "Login disabled for local development."
        if _LOGIN_DISABLED
        else "Operator not authenticated."
    )
    failed_login_attempts: int = 0
    login_lockout_until: str = ""
    admin_recovery_key_input: str = ""
    admin_recovery_notice: str = ""

    def update_login_username_input(self, value: str):
        self.login_username_input = value

    def update_login_password_input(self, value: str):
        self.login_password_input = value

    def update_admin_recovery_key_input(self, value: str):
        self.admin_recovery_key_input = value

    @staticmethod
    def _max_login_attempts() -> int:
        try:
            return max(1, int(os.getenv("OPENSIGNAL_MAX_LOGIN_ATTEMPTS", "5")))
        except ValueError:
            return 5

    @staticmethod
    def _login_lockout_seconds() -> int:
        try:
            return max(10, int(os.getenv("OPENSIGNAL_LOGIN_LOCKOUT_SECONDS", "300")))
        except ValueError:
            return 300

    def _actor_name(self) -> str:
        if self.current_operator:
            return f"{self.current_operator}:{self.current_role}"
        return "anonymous"

    def _is_role_authorized(self, allowed_roles: set[str]) -> bool:
        if _LOGIN_DISABLED:
            return True
        if not self.is_authenticated:
            return False
        return OperatorAuthService.role_authorized(self.current_role, allowed_roles)

    def _is_login_locked(self) -> bool:
        if not self.login_lockout_until:
            return False
        return not self._has_expired(self.login_lockout_until)

    def login_operator(self):
        if _LOGIN_DISABLED:
            self.is_authenticated = True
            self.current_operator = _LOGIN_BYPASS_OPERATOR
            self.current_role = "admin"
            self.auth_notice = "Login is disabled; using local admin session."
            self.error = ""
            self.failed_login_attempts = 0
            self.login_lockout_until = ""
            self.login_password_input = ""
            return

        if self._is_login_locked():
            self.is_authenticated = False
            self.current_operator = ""
            self.current_role = "viewer"
            self.auth_notice = "Operator login temporarily locked due to repeated failures."
            self.error = self.auth_notice
            self.login_password_input = ""
            return

        success, message, role = OperatorAuthService.authenticate_with_role(
            username=self.login_username_input,
            password=self.login_password_input,
        )
        self.is_authenticated = success
        if success:
            self.current_operator = self.login_username_input.strip()
            self.current_role = role
            self.auth_notice = f"Authenticated as {self.current_operator} ({self.current_role})."
            self.error = ""
            self.failed_login_attempts = 0
            self.login_lockout_until = ""
        else:
            self.current_operator = ""
            self.current_role = "viewer"
            self.failed_login_attempts += 1
            if self.failed_login_attempts >= self._max_login_attempts():
                lockout_seconds = self._login_lockout_seconds()
                self.login_lockout_until = self._utc_future_iso(lockout_seconds)
                self.auth_notice = (
                    "Operator login temporarily locked due to repeated failures."
                )
                self.error = self.auth_notice
            else:
                self.auth_notice = message
                self.error = message
            self.lock_write_mode()
        self.login_password_input = ""

    def logout_operator(self):
        if _LOGIN_DISABLED:
            self.is_authenticated = True
            self.current_operator = _LOGIN_BYPASS_OPERATOR
            self.current_role = "admin"
            self.auth_notice = "Login remains disabled for local development."
            self.login_password_input = ""
            self.operator_key_input = ""
            self.error = ""
            return

        self.is_authenticated = False
        self.current_operator = ""
        self.current_role = "viewer"
        self.auth_notice = "Operator not authenticated."
        self.login_password_input = ""
        self.operator_key_input = ""
        self.lock_write_mode()

    def reset_login_lockout(self):
        if _LOGIN_DISABLED:
            self.failed_login_attempts = 0
            self.login_lockout_until = ""
            self.admin_recovery_notice = "Login is disabled; lockout reset is not required."
            self.error = ""
            return

        ok, message = OperatorAuthService.validate_admin_recovery_key(self.admin_recovery_key_input)
        self.admin_recovery_key_input = ""
        if not ok:
            self.admin_recovery_notice = message
            self.error = message
            return
        self.failed_login_attempts = 0
        self.login_lockout_until = ""
        self.admin_recovery_notice = "Login lockout reset by admin recovery key."
        self.error = ""