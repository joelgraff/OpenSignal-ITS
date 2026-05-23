import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from opensignal_its.db.audit_store import AuditStore
from opensignal_its.services import alert_dispatch_service
from opensignal_its.services.alert_dispatch_service import AlertDispatchService


class AlertDispatchServiceTests(unittest.TestCase):
    def setUp(self):
        self._env = {
            "OPENSIGNAL_ALERT_WEBHOOK_ENABLED": os.environ.get("OPENSIGNAL_ALERT_WEBHOOK_ENABLED"),
            "OPENSIGNAL_ALERT_WEBHOOK_URL": os.environ.get("OPENSIGNAL_ALERT_WEBHOOK_URL"),
            "OPENSIGNAL_ALERT_WEBHOOK_DEDUP_SECONDS": os.environ.get("OPENSIGNAL_ALERT_WEBHOOK_DEDUP_SECONDS"),
            "OPENSIGNAL_ALERT_WEBHOOK_TIMEOUT_SECONDS": os.environ.get("OPENSIGNAL_ALERT_WEBHOOK_TIMEOUT_SECONDS"),
            "OPENSIGNAL_ALERT_WEBHOOK_MAX_RETRIES": os.environ.get("OPENSIGNAL_ALERT_WEBHOOK_MAX_RETRIES"),
        }
        self._tmp = tempfile.TemporaryDirectory()
        self._store = AuditStore(str(Path(self._tmp.name) / "audit.db"))
        self._original_store = alert_dispatch_service.STORE
        alert_dispatch_service.STORE = self._store
        AlertDispatchService.reset_state()

    def tearDown(self):
        for key, value in self._env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        alert_dispatch_service.STORE = self._original_store
        self._tmp.cleanup()
        AlertDispatchService.reset_state()

    def test_dispatch_disabled_when_not_enabled(self):
        os.environ["OPENSIGNAL_ALERT_WEBHOOK_ENABLED"] = "false"
        result = AlertDispatchService.dispatch_persistent_alerts(["a1"], {})
        self.assertFalse(bool(result["enabled"]))
        self.assertEqual(1, int(result["skipped"]))

    def test_dispatch_sends_and_dedups(self):
        os.environ["OPENSIGNAL_ALERT_WEBHOOK_ENABLED"] = "true"
        os.environ["OPENSIGNAL_ALERT_WEBHOOK_URL"] = "https://example.invalid/webhook"
        os.environ["OPENSIGNAL_ALERT_WEBHOOK_DEDUP_SECONDS"] = "300"

        with patch.object(AlertDispatchService, "_post_json", return_value=True) as mocked:
            first = AlertDispatchService.dispatch_persistent_alerts(["alert-1"], {"x": 1})
            second = AlertDispatchService.dispatch_persistent_alerts(["alert-1"], {"x": 1})

        self.assertEqual(1, int(first["sent"]))
        self.assertEqual(0, int(first["failed"]))
        self.assertEqual(0, int(first["skipped"]))
        self.assertEqual(0, int(second["sent"]))
        self.assertEqual(1, int(second["skipped"]))
        self.assertEqual(1, mocked.call_count)

    def test_dispatch_retries_and_reports_failure(self):
        os.environ["OPENSIGNAL_ALERT_WEBHOOK_ENABLED"] = "true"
        os.environ["OPENSIGNAL_ALERT_WEBHOOK_URL"] = "https://example.invalid/webhook"
        os.environ["OPENSIGNAL_ALERT_WEBHOOK_MAX_RETRIES"] = "2"

        with patch.object(AlertDispatchService, "_post_json", return_value=False) as mocked:
            result = AlertDispatchService.dispatch_persistent_alerts(["alert-2"], {})

        self.assertEqual(0, int(result["sent"]))
        self.assertEqual(1, int(result["failed"]))
        self.assertEqual(1, int(result["deadlettered"]))
        self.assertEqual(3, mocked.call_count)
        self.assertEqual(1, len(self._store.list_alert_webhook_deadletter(limit=10)))


if __name__ == "__main__":
    unittest.main()
