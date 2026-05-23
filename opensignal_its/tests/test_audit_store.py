import sqlite3
import tempfile
import unittest
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from opensignal_its.db.audit_store import AuditStore, CommandAuditRecord


class AuditStoreTests(unittest.TestCase):
    def test_writes_command_and_snapshot_with_correlation(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "audit.db"
            store = AuditStore(str(db_path))

            store.log_command(
                CommandAuditRecord(
                    timestamp="2026-01-01T00:00:00",
                    correlation_id="corr-1",
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
                payload={"is_online": True, "status_text": "ok"},
                correlation_id="corr-1",
                source="command",
            )

            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("SELECT correlation_id, actor FROM command_audit LIMIT 1")
            cmd_row = cur.fetchone()
            cur.execute("SELECT correlation_id, source FROM status_snapshots LIMIT 1")
            snap_row = cur.fetchone()
            conn.close()

            self.assertEqual(("corr-1", "alice"), cmd_row)
            self.assertEqual(("corr-1", "command"), snap_row)

    def test_retention_cleanup_removes_old_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "audit.db"
            store = AuditStore(str(db_path))

            old_ts = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
            new_ts = datetime.now(timezone.utc).isoformat()

            store.log_command(
                CommandAuditRecord(
                    timestamp=old_ts,
                    correlation_id="old",
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
            store.log_command(
                CommandAuditRecord(
                    timestamp=new_ts,
                    correlation_id="new",
                    device_ip="10.0.0.1",
                    command_type="set_mode",
                    command_value={"mode": "coordinated"},
                    probe_only=False,
                    allowed=True,
                    success=True,
                    error="",
                    actor="alice",
                )
            )

            store.log_status_snapshot(
                device_ip="10.0.0.1",
                payload={"timestamp": old_ts, "is_online": True, "status_text": "old"},
                correlation_id="old",
                source="poll",
            )
            store.log_status_snapshot(
                device_ip="10.0.0.1",
                payload={"timestamp": new_ts, "is_online": True, "status_text": "new"},
                correlation_id="new",
                source="poll",
            )

            deleted_commands, deleted_snapshots = store.purge_old_records(
                command_retention_days=30,
                snapshot_retention_days=30,
            )

            self.assertEqual(1, deleted_commands)
            self.assertEqual(1, deleted_snapshots)

            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM command_audit")
            remaining_commands = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM status_snapshots")
            remaining_snapshots = cur.fetchone()[0]
            conn.close()

            self.assertEqual(1, remaining_commands)
            self.assertEqual(1, remaining_snapshots)

    def test_export_activity_report_writes_json_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            db_path = base / "audit.db"
            report_path = base / "reports" / "runtime.json"
            store = AuditStore(str(db_path))

            store.log_command(
                CommandAuditRecord(
                    timestamp="2026-01-01T00:00:00+00:00",
                    correlation_id="corr-export",
                    device_ip="10.0.0.1",
                    command_type="set_mode",
                    command_value={"mode": "free"},
                    probe_only=False,
                    allowed=True,
                    success=True,
                    error="",
                    actor="admin:admin",
                )
            )
            exported = store.export_activity_report(
                file_path=str(report_path),
                command_limit=10,
                snapshot_limit=10,
                metadata={"role": "admin"},
            )

            payload = json.loads(Path(exported).read_text(encoding="utf-8"))
            self.assertEqual("admin", payload["metadata"]["role"])
            self.assertEqual(1, len(payload["commands"]))


if __name__ == "__main__":
    unittest.main()
