"""Audit export state slice."""

from __future__ import annotations

import os

from ..db import STORE


class AuditStateMixin:
    audit_export_notice: str = ""
    audit_export_path: str = ""

    def export_audit_report(self):
        if not self._is_role_authorized({"admin"}):
            self.audit_export_notice = "Audit export denied: admin authentication required."
            self.error = self.audit_export_notice
            return

        target_path = os.getenv("OPENSIGNAL_AUDIT_EXPORT_PATH", "runtime_reports/latest_runtime_report.json")
        metadata = {
            "operator": self.current_operator,
            "role": self.current_role,
            "runtime_health": self.runtime_health_notice,
            "scheduler_enabled": self.retention_scheduler_enabled,
            "scheduler_running": self.retention_scheduler_running,
            "scheduler_interval_seconds": self.retention_scheduler_interval_text,
        }
        try:
            exported_path = STORE.export_activity_report(
                file_path=target_path,
                command_limit=200,
                snapshot_limit=200,
                metadata=metadata,
            )
            self.audit_export_path = exported_path
            self.audit_export_notice = f"Audit report exported to {exported_path}."
            self.error = ""
        except Exception as exc:
            self.audit_export_notice = f"Audit report export failed: {exc}"
            self.error = self.audit_export_notice