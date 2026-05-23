import os
import tempfile
import unittest
from pathlib import Path

from opensignal_its.db.audit_store import AuditStore
from opensignal_its.services import preflight_service


class PreflightServiceTests(unittest.TestCase):
    def setUp(self):
        self._keys = {
            "OPENSIGNAL_ENV": os.environ.get("OPENSIGNAL_ENV"),
            "OPENSIGNAL_OPERATOR_PASSWORD": os.environ.get("OPENSIGNAL_OPERATOR_PASSWORD"),
            "OPENSIGNAL_OPERATOR_PASSWORD_HASH": os.environ.get("OPENSIGNAL_OPERATOR_PASSWORD_HASH"),
            "OPENSIGNAL_OPERATOR_KEY": os.environ.get("OPENSIGNAL_OPERATOR_KEY"),
            "OPENSIGNAL_OPERATOR_KEY_HASH": os.environ.get("OPENSIGNAL_OPERATOR_KEY_HASH"),
            "OPENSIGNAL_ADMIN_PASSWORD": os.environ.get("OPENSIGNAL_ADMIN_PASSWORD"),
            "OPENSIGNAL_ADMIN_PASSWORD_HASH": os.environ.get("OPENSIGNAL_ADMIN_PASSWORD_HASH"),
            "OPENSIGNAL_ADMIN_RECOVERY_KEY": os.environ.get("OPENSIGNAL_ADMIN_RECOVERY_KEY"),
            "OPENSIGNAL_ADMIN_RECOVERY_KEY_HASH": os.environ.get("OPENSIGNAL_ADMIN_RECOVERY_KEY_HASH"),
            "OPENSIGNAL_COMMAND_RETENTION_DAYS": os.environ.get("OPENSIGNAL_COMMAND_RETENTION_DAYS"),
            "OPENSIGNAL_SNAPSHOT_RETENTION_DAYS": os.environ.get("OPENSIGNAL_SNAPSHOT_RETENTION_DAYS"),
            "OPENSIGNAL_APPLY_RETENTION_ON_START": os.environ.get("OPENSIGNAL_APPLY_RETENTION_ON_START"),
            "OPENSIGNAL_ENABLE_RETENTION_SCHEDULER": os.environ.get("OPENSIGNAL_ENABLE_RETENTION_SCHEDULER"),
            "OPENSIGNAL_RETENTION_SCHEDULE_SECONDS": os.environ.get("OPENSIGNAL_RETENTION_SCHEDULE_SECONDS"),
        }

    def tearDown(self):
        for key, value in self._keys.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_validate_requires_secrets_in_production_mode(self):
        os.environ["OPENSIGNAL_ENV"] = "production"
        os.environ.pop("OPENSIGNAL_OPERATOR_PASSWORD", None)
        os.environ.pop("OPENSIGNAL_OPERATOR_KEY", None)
        os.environ.pop("OPENSIGNAL_ADMIN_PASSWORD", None)
        os.environ.pop("OPENSIGNAL_ADMIN_RECOVERY_KEY", None)
        errors = preflight_service.validate_runtime_configuration()
        self.assertTrue(any("OPENSIGNAL_OPERATOR_PASSWORD" in e for e in errors))
        self.assertTrue(any("OPENSIGNAL_OPERATOR_KEY" in e for e in errors))
        self.assertTrue(any("OPENSIGNAL_ADMIN_PASSWORD" in e for e in errors))
        self.assertTrue(any("OPENSIGNAL_ADMIN_RECOVERY_KEY" in e for e in errors))

    def test_validate_accepts_dev_without_secrets(self):
        os.environ["OPENSIGNAL_ENV"] = "dev"
        os.environ.pop("OPENSIGNAL_OPERATOR_PASSWORD", None)
        os.environ.pop("OPENSIGNAL_OPERATOR_KEY", None)
        errors = preflight_service.validate_runtime_configuration()
        self.assertEqual([], errors)

    def test_bootstrap_raises_on_invalid_retention_values(self):
        os.environ["OPENSIGNAL_ENV"] = "dev"
        os.environ["OPENSIGNAL_COMMAND_RETENTION_DAYS"] = "0"
        with self.assertRaises(RuntimeError):
            preflight_service.bootstrap_runtime_safety()

    def test_bootstrap_applies_retention_when_enabled(self):
        os.environ["OPENSIGNAL_ENV"] = "dev"
        os.environ["OPENSIGNAL_COMMAND_RETENTION_DAYS"] = "30"
        os.environ["OPENSIGNAL_SNAPSHOT_RETENTION_DAYS"] = "30"
        os.environ["OPENSIGNAL_APPLY_RETENTION_ON_START"] = "true"

        with tempfile.TemporaryDirectory() as tmp:
            store = AuditStore(str(Path(tmp) / "audit.db"))
            original_store = preflight_service.STORE
            preflight_service.STORE = store
            try:
                preflight_service.bootstrap_runtime_safety()
            finally:
                preflight_service.STORE = original_store

    def test_validate_rejects_scheduler_interval_below_minimum(self):
        os.environ["OPENSIGNAL_ENV"] = "dev"
        os.environ["OPENSIGNAL_ENABLE_RETENTION_SCHEDULER"] = "true"
        os.environ["OPENSIGNAL_RETENTION_SCHEDULE_SECONDS"] = "120"
        errors = preflight_service.validate_runtime_configuration()
        self.assertTrue(any("OPENSIGNAL_RETENTION_SCHEDULE_SECONDS" in e for e in errors))

    def test_validate_rejects_short_plaintext_secrets_in_production(self):
        os.environ["OPENSIGNAL_ENV"] = "production"
        os.environ["OPENSIGNAL_OPERATOR_PASSWORD"] = "short"
        os.environ["OPENSIGNAL_OPERATOR_KEY"] = "short"
        os.environ["OPENSIGNAL_ADMIN_PASSWORD"] = "short"
        os.environ["OPENSIGNAL_ADMIN_RECOVERY_KEY"] = "short"
        errors = preflight_service.validate_runtime_configuration()
        self.assertTrue(any("at least 12 chars" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
