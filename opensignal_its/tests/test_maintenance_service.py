import tempfile
import unittest
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from opensignal_its.db.audit_store import AuditStore
from opensignal_its.services import maintenance_service


class MaintenanceServiceTests(unittest.TestCase):
    def test_run_retention_cleanup_uses_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = AuditStore(str(Path(tmp) / "audit.db"))
            original_store = maintenance_service.STORE
            maintenance_service.STORE = store
            try:
                result = maintenance_service.MaintenanceService.run_retention_cleanup()
            finally:
                maintenance_service.STORE = original_store

            self.assertIsInstance(result, tuple)
            self.assertEqual(2, len(result))

    def test_cleanup_status_updates_after_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = AuditStore(str(Path(tmp) / "audit.db"))
            original_store = maintenance_service.STORE
            maintenance_service.STORE = store
            try:
                maintenance_service.MaintenanceService.run_retention_cleanup()
                status = maintenance_service.MaintenanceService.get_cleanup_status()
            finally:
                maintenance_service.STORE = original_store

        self.assertTrue(status["last_run_at"])
        self.assertIn("Retention cleanup", status["message"])
        self.assertIn("ok", status)

    def test_cleanup_removes_expired_alarm_silences(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "audit.db"
            store = AuditStore(str(db_path))
            original_store = maintenance_service.STORE
            maintenance_service.STORE = store
            try:
                key = "ALARM severity=critical type=offline-streak device=10.0.0.1 threshold=2"
                store.silence_alarm(key, "alice:admin", 10)

                expired_ts = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
                import sqlite3

                conn = sqlite3.connect(db_path)
                conn.execute(
                    "UPDATE alarm_silences SET silenced_until = ? WHERE alarm_key = ?",
                    (expired_ts, key),
                )
                conn.commit()
                conn.close()

                maintenance_service.MaintenanceService.run_retention_cleanup()
                status = maintenance_service.MaintenanceService.get_cleanup_status()
            finally:
                maintenance_service.STORE = original_store

        self.assertIn("expired alarm silences deleted", status["message"])
        self.assertGreaterEqual(int(status.get("deleted_alarm_silences", 0)), 1)

    def test_cleanup_removes_old_alarm_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "audit.db"
            store = AuditStore(str(db_path))
            original_store = maintenance_service.STORE
            original_days = os.environ.get("OPENSIGNAL_ALARM_EVENT_RETENTION_DAYS")
            maintenance_service.STORE = store
            os.environ["OPENSIGNAL_ALARM_EVENT_RETENTION_DAYS"] = "30"
            try:
                key = "ALARM severity=high type=command-failure-streak device=10.0.0.1 threshold=2"
                store.log_alarm_event(key, "acknowledge", "alice:admin", "old")

                import sqlite3

                old_ts = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
                conn = sqlite3.connect(db_path)
                conn.execute(
                    "UPDATE alarm_events SET timestamp = ? WHERE alarm_key = ?",
                    (old_ts, key),
                )
                conn.commit()
                conn.close()

                maintenance_service.MaintenanceService.run_retention_cleanup()
                status = maintenance_service.MaintenanceService.get_cleanup_status()
            finally:
                maintenance_service.STORE = original_store
                if original_days is None:
                    os.environ.pop("OPENSIGNAL_ALARM_EVENT_RETENTION_DAYS", None)
                else:
                    os.environ["OPENSIGNAL_ALARM_EVENT_RETENTION_DAYS"] = original_days

        self.assertIn("alarm events deleted", status["message"])
        self.assertGreaterEqual(int(status.get("deleted_alarm_events", 0)), 1)


if __name__ == "__main__":
    unittest.main()
