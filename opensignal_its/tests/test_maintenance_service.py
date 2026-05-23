import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
