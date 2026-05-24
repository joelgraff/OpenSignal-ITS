import hashlib
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from opensignal_its.db.audit_store import AuditStore
from opensignal_its.services import event_service
from opensignal_its.services.alert_dispatch_service import AlertDispatchService
from opensignal_its.services import ops_api_service
from opensignal_its.services.ops_api_service import OpsApiService


class OpsApiServiceTests(unittest.TestCase):
    def setUp(self):
        self._env = {
            "OPENSIGNAL_OPS_API_ENABLED": os.environ.get("OPENSIGNAL_OPS_API_ENABLED"),
            "OPENSIGNAL_OPS_API_TOKEN": os.environ.get("OPENSIGNAL_OPS_API_TOKEN"),
            "OPENSIGNAL_OPS_API_TOKEN_HASH": os.environ.get("OPENSIGNAL_OPS_API_TOKEN_HASH"),
            "OPENSIGNAL_OPS_API_TOKEN_HASHES": os.environ.get("OPENSIGNAL_OPS_API_TOKEN_HASHES"),
            "OPENSIGNAL_OPS_API_ALLOW_UNAUTHENTICATED": os.environ.get("OPENSIGNAL_OPS_API_ALLOW_UNAUTHENTICATED"),
            "OPENSIGNAL_AUDIT_EXPORT_DIR": os.environ.get("OPENSIGNAL_AUDIT_EXPORT_DIR"),
            "OPENSIGNAL_AUDIT_EXPORT_PATH": os.environ.get("OPENSIGNAL_AUDIT_EXPORT_PATH"),
            "OPENSIGNAL_DB_WARN_COMMAND_AUDIT_ROWS": os.environ.get("OPENSIGNAL_DB_WARN_COMMAND_AUDIT_ROWS"),
            "OPENSIGNAL_DB_WARN_STATUS_SNAPSHOTS_ROWS": os.environ.get("OPENSIGNAL_DB_WARN_STATUS_SNAPSHOTS_ROWS"),
            "OPENSIGNAL_DB_WARN_ALARM_ACK_ROWS": os.environ.get("OPENSIGNAL_DB_WARN_ALARM_ACK_ROWS"),
            "OPENSIGNAL_DB_WARN_ALARM_SILENCES_ROWS": os.environ.get("OPENSIGNAL_DB_WARN_ALARM_SILENCES_ROWS"),
            "OPENSIGNAL_DB_WARN_ALARM_EVENTS_ROWS": os.environ.get("OPENSIGNAL_DB_WARN_ALARM_EVENTS_ROWS"),
            "OPENSIGNAL_DB_WARN_ALERT_WEBHOOK_QUEUE_ROWS": os.environ.get("OPENSIGNAL_DB_WARN_ALERT_WEBHOOK_QUEUE_ROWS"),
            "OPENSIGNAL_DB_WARN_ALERT_WEBHOOK_DEADLETTER_ROWS": os.environ.get("OPENSIGNAL_DB_WARN_ALERT_WEBHOOK_DEADLETTER_ROWS"),
            "OPENSIGNAL_DB_WARN_PERSISTENCE_CHECKS": os.environ.get("OPENSIGNAL_DB_WARN_PERSISTENCE_CHECKS"),
            "OPENSIGNAL_ALERT_WEBHOOK_ENABLED": os.environ.get("OPENSIGNAL_ALERT_WEBHOOK_ENABLED"),
            "OPENSIGNAL_ALERT_WEBHOOK_URL": os.environ.get("OPENSIGNAL_ALERT_WEBHOOK_URL"),
            "OPENSIGNAL_ALERT_WEBHOOK_MAX_RETRIES": os.environ.get("OPENSIGNAL_ALERT_WEBHOOK_MAX_RETRIES"),
        }
        OpsApiService.reset_warning_state()
        AlertDispatchService.reset_state()

    def tearDown(self):
        for key, value in self._env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        AlertDispatchService.reset_state()

    def test_health_snapshot_shape(self):
        payload = OpsApiService.health_snapshot()
        self.assertIn("generated_at", payload)
        self.assertIn("runtime", payload)
        self.assertIn("scheduler", payload)
        self.assertIn("retention_cleanup", payload)
        self.assertIn("storage", payload)
        self.assertIn("table_row_counts", payload["storage"])
        self.assertIn("warning_thresholds", payload["storage"])
        self.assertIn("warning_details", payload["storage"])
        self.assertIn("warning_persistence_checks", payload["storage"])
        self.assertIn("warnings", payload["storage"])
        self.assertIn("persistent_alerts", payload["storage"])
        self.assertIn("alert_dispatch", payload["storage"])

    def test_health_snapshot_emits_storage_warnings_when_thresholds_exceeded(self):
        os.environ["OPENSIGNAL_DB_WARN_ALARM_EVENTS_ROWS"] = "1"

        with tempfile.TemporaryDirectory() as tmp:
            store = AuditStore(str(Path(tmp) / "audit.db"))
            original_store = event_service.STORE
            event_service.STORE = store
            try:
                store.log_alarm_event(
                    alarm_key="ALARM severity=high type=command-failure-streak device=10.0.0.9 threshold=2",
                    action="acknowledge",
                    actor="alice:admin",
                    note="test",
                )
                payload = OpsApiService.health_snapshot()
            finally:
                event_service.STORE = original_store

        warnings = list(payload["storage"].get("warnings", []))
        self.assertTrue(any("alarm_events" in row for row in warnings))

    def test_health_snapshot_emits_persistent_alerts_after_streak(self):
        os.environ["OPENSIGNAL_DB_WARN_ALARM_EVENTS_ROWS"] = "1"
        os.environ["OPENSIGNAL_DB_WARN_PERSISTENCE_CHECKS"] = "2"

        with tempfile.TemporaryDirectory() as tmp:
            store = AuditStore(str(Path(tmp) / "audit.db"))
            original_store = event_service.STORE
            event_service.STORE = store
            try:
                store.log_alarm_event(
                    alarm_key="ALARM severity=high type=command-failure-streak device=10.0.0.9 threshold=2",
                    action="acknowledge",
                    actor="alice:admin",
                    note="test",
                )
                first = OpsApiService.health_snapshot()
                second = OpsApiService.health_snapshot()
            finally:
                event_service.STORE = original_store

        self.assertEqual([], list(first["storage"].get("persistent_alerts", [])))
        self.assertTrue(
            any("alarm_events" in row for row in list(second["storage"].get("persistent_alerts", [])))
        )

    def test_health_snapshot_dispatches_persistent_alert_when_enabled(self):
        os.environ["OPENSIGNAL_DB_WARN_ALARM_EVENTS_ROWS"] = "1"
        os.environ["OPENSIGNAL_DB_WARN_PERSISTENCE_CHECKS"] = "1"
        os.environ["OPENSIGNAL_ALERT_WEBHOOK_ENABLED"] = "true"
        os.environ["OPENSIGNAL_ALERT_WEBHOOK_URL"] = "https://example.invalid/webhook"
        os.environ["OPENSIGNAL_ALERT_WEBHOOK_MAX_RETRIES"] = "0"

        with tempfile.TemporaryDirectory() as tmp:
            store = AuditStore(str(Path(tmp) / "audit.db"))
            original_store = event_service.STORE
            event_service.STORE = store
            try:
                store.log_alarm_event(
                    alarm_key="ALARM severity=high type=command-failure-streak device=10.0.0.99 threshold=2",
                    action="acknowledge",
                    actor="alice:admin",
                    note="test",
                )
                with patch.object(AlertDispatchService, "_post_json", return_value=True) as mocked:
                    payload = OpsApiService.health_snapshot()
            finally:
                event_service.STORE = original_store

        dispatch = dict(payload["storage"].get("alert_dispatch", {}))
        self.assertTrue(bool(dispatch.get("enabled", False)))
        self.assertEqual(1, int(dispatch.get("sent", 0)))
        self.assertEqual(1, mocked.call_count)

    def test_validate_access_rejects_when_disabled(self):
        os.environ["OPENSIGNAL_OPS_API_ENABLED"] = "false"
        ok, message = OpsApiService.validate_access(api_token="")
        self.assertFalse(ok)
        self.assertIn("disabled", message)

    def test_validate_access_accepts_plain_and_hash_tokens(self):
        os.environ["OPENSIGNAL_OPS_API_ENABLED"] = "true"
        os.environ["OPENSIGNAL_OPS_API_TOKEN"] = "plain-token"
        digest = hashlib.sha256("hash-token".encode("utf-8")).hexdigest()
        os.environ["OPENSIGNAL_OPS_API_TOKEN_HASH"] = f"sha256:{digest}"

        ok_plain, _ = OpsApiService.validate_access(api_token="plain-token")
        ok_hash, _ = OpsApiService.validate_access(api_token="hash-token")
        bad, _ = OpsApiService.validate_access(api_token="bad-token")

        self.assertTrue(ok_plain)
        self.assertTrue(ok_hash)
        self.assertFalse(bad)

    def test_validate_access_requires_token_configuration_by_default(self):
        os.environ["OPENSIGNAL_OPS_API_ENABLED"] = "true"
        os.environ.pop("OPENSIGNAL_OPS_API_TOKEN", None)
        os.environ.pop("OPENSIGNAL_OPS_API_TOKEN_HASH", None)
        os.environ.pop("OPENSIGNAL_OPS_API_TOKEN_HASHES", None)
        os.environ["OPENSIGNAL_OPS_API_ALLOW_UNAUTHENTICATED"] = "false"

        ok, message = OpsApiService.validate_access(api_token="")

        self.assertFalse(ok)
        self.assertIn("token configuration required", message)

    def test_validate_access_allows_unauthenticated_override(self):
        os.environ["OPENSIGNAL_OPS_API_ENABLED"] = "true"
        os.environ.pop("OPENSIGNAL_OPS_API_TOKEN", None)
        os.environ.pop("OPENSIGNAL_OPS_API_TOKEN_HASH", None)
        os.environ.pop("OPENSIGNAL_OPS_API_TOKEN_HASHES", None)
        os.environ["OPENSIGNAL_OPS_API_ALLOW_UNAUTHENTICATED"] = "true"

        ok, message = OpsApiService.validate_access(api_token="")

        self.assertTrue(ok)
        self.assertIn("unauthenticated override", message)

    def test_extract_api_token_prefers_bearer_authorization(self):
        token = OpsApiService.extract_api_token(
            api_token="query-token",
            authorization="Bearer header-token",
        )
        self.assertEqual("header-token", token)

    def test_alarms_and_history_snapshots(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = AuditStore(str(Path(tmp) / "audit.db"))
            original_store = event_service.STORE
            event_service.STORE = store
            try:
                now = datetime.now(timezone.utc)
                ts1 = (now - timedelta(minutes=2)).isoformat()
                ts2 = (now - timedelta(minutes=1)).isoformat()
                store.log_status_snapshot(
                    device_ip="10.0.0.99",
                    payload={"timestamp": ts1, "is_online": False, "status_text": "offline"},
                )
                store.log_status_snapshot(
                    device_ip="10.0.0.99",
                    payload={"timestamp": ts2, "is_online": False, "status_text": "offline"},
                )

                alarm_key = (
                    "ALARM severity=critical type=offline-streak "
                    "device=10.0.0.99 threshold=3"
                )
                store.acknowledge_alarm(alarm_key, "alice:admin", "ack")

                alarms = OpsApiService.alarms_snapshot(window_minutes=None, command_limit=50, snapshot_limit=50)
                history = OpsApiService.alarm_history_snapshot(limit=10, action_filter="acknowledge")
            finally:
                event_service.STORE = original_store

        self.assertIn("payload", alarms)
        self.assertIn("active_count", alarms)
        self.assertIn("rows", history)
        self.assertGreaterEqual(history["count"], 1)

    def test_audit_export_snapshot_writes_report_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = AuditStore(str(Path(tmp) / "audit.db"))
            original_store = ops_api_service.STORE
            ops_api_service.STORE = store
            try:
                os.environ["OPENSIGNAL_AUDIT_EXPORT_DIR"] = str(Path(tmp) / "exports")
                report_path = "ops/audit-report.json"
                payload = OpsApiService.audit_export_snapshot(
                    file_path=report_path,
                    command_limit=5,
                    snapshot_limit=5,
                )
            finally:
                ops_api_service.STORE = original_store

        self.assertTrue(str(payload["file_path"]).startswith(str(Path(tmp) / "exports")))
        self.assertEqual(5, int(payload["command_limit"]))
        self.assertEqual(5, int(payload["snapshot_limit"]))

    def test_audit_export_snapshot_rejects_path_outside_export_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = AuditStore(str(Path(tmp) / "audit.db"))
            original_store = ops_api_service.STORE
            ops_api_service.STORE = store
            try:
                os.environ["OPENSIGNAL_AUDIT_EXPORT_DIR"] = str(Path(tmp) / "exports")
                outside = str(Path(tmp) / "outside" / "bad.json")
                with self.assertRaises(ValueError):
                    OpsApiService.audit_export_snapshot(file_path=outside)
            finally:
                ops_api_service.STORE = original_store


if __name__ == "__main__":
    unittest.main()
