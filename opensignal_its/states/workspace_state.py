"""Workspace shell navigation state slice."""

from __future__ import annotations


class WorkspaceStateMixin:
    ui_workspace_mode: str = "monitor"

    def update_ui_workspace_mode(self, value: str):
        normalized = value.strip().lower()
        if normalized in {"monitor", "control", "operations", "analytics", "configuration", "admin"}:
            self.ui_workspace_mode = normalized
            if normalized == "configuration":
                self._sync_controller_profile_rows()