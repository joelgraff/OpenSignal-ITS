import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from opensignal_its.db.audit_store import AuditStore
from opensignal_its.db.audit_store import CommandAuditRecord
from opensignal_its.services.auth_service import OperatorAuthService
from opensignal_its.services.safety_service import CommandSafetyService


class SecurityFlowServiceTests(unittest.TestCase):
    def setUp(self):
        self._old_env = {
            "OPENSIGNAL_OPERATOR_USERNAME": os.environ.get("OPENSIGNAL_OPERATOR_USERNAME"),
            "OPENSIGNAL_OPERATOR_PASSWORD": os.environ.get("OPENSIGNAL_OPERATOR_PASSWORD"),
            "OPENSIGNAL_OPERATOR_KEY": os.environ.get("OPENSIGNAL_OPERATOR_KEY"),
        }

    def tearDown(self):
        for key, value in self._old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_authenticated_unlock_and_correlated_audit_records(self):
        os.environ["OPENSIGNAL_OPERATOR_USERNAME"] = "alice"
        os.environ["OPENSIGNAL_OPERATOR_PASSWORD"] = "secret"
        os.environ["OPENSIGNAL_OPERATOR_KEY"] = "unlock"

        ok, message = OperatorAuthService.authenticate("alice", "secret")
        self.assertTrue(ok)
        self.assertIn("successful", message)

        unlock_ok, unlock_message, unlock_until = CommandSafetyService.unlock_write_mode(
            operator_key_input="unlock",
            requested_seconds=60,
        )
        self.assertTrue(unlock_ok)
        self.assertNotEqual("", unlock_until)
        self.assertIn("unlocked", unlock_message)

        safety = CommandSafetyService.evaluate_command(
            safe_command_probe=False,
            write_unlock_until=unlock_until,
        )
        self.assertTrue(safety.allowed)

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "audit.db"
            store = AuditStore(str(db_path))
            correlation_id = uuid4().hex

            store.log_command(
                CommandAuditRecord(
                    timestamp="2026-01-01T00:00:00",
                    correlation_id=correlation_id,
                    device_ip="10.0.0.1",
                    command_type="set_mode",
                    command_value={"mode": "free"},
                    probe_only=False,
                    allowed=True,
                    success=True,
                    error="",
                    actor="alice",
                )
            )
            store.log_status_snapshot(
                device_ip="10.0.0.1",
                payload={"timestamp": "2026-01-01T00:00:01", "is_online": True, "status_text": "ok"},
                correlation_id=correlation_id,
                source="command",
            )

            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute(
                "SELECT correlation_id FROM command_audit WHERE allowed = 1 AND success = 1 ORDER BY id DESC LIMIT 1"
            )
            command_row = cur.fetchone()
            self.assertIsNotNone(command_row)
            correlation_id = command_row[0]
            self.assertTrue(correlation_id)

            cur.execute(
                "SELECT correlation_id, source FROM status_snapshots WHERE source = 'command' ORDER BY id DESC LIMIT 1"
            )
            snapshot_row = cur.fetchone()
            conn.close()

            self.assertIsNotNone(snapshot_row)
            self.assertEqual((correlation_id, "command"), snapshot_row)

    def test_unlock_denied_for_invalid_key(self):
        os.environ["OPENSIGNAL_OPERATOR_USERNAME"] = "alice"
        os.environ["OPENSIGNAL_OPERATOR_PASSWORD"] = "secret"
        os.environ["OPENSIGNAL_OPERATOR_KEY"] = "unlock"

        unlock_ok, unlock_message, unlock_until = CommandSafetyService.unlock_write_mode(
            operator_key_input="bad",
            requested_seconds=60,
        )
        self.assertFalse(unlock_ok)
        self.assertEqual("", unlock_until)
        self.assertIn("invalid", unlock_message)


if __name__ == "__main__":
    unittest.main()
