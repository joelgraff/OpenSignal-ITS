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

    def test_alarm_ack_and_silence_persistence_and_expiry_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "audit.db"
            store = AuditStore(str(db_path))

            alarm_key = "ALARM severity=critical type=offline-streak device=10.0.0.1 threshold=2"
            store.acknowledge_alarm(alarm_key, "alice:admin", "acknowledged")
            acks = store.list_alarm_acknowledgements()
            self.assertIn(alarm_key, acks)

            store.silence_alarm(alarm_key, "alice:admin", 30, "maintenance window")
            silences = store.list_alarm_silences()
            self.assertIn(alarm_key, silences)

            # Force one row into expired state and validate filtering.
            expired_ts = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
            conn = sqlite3.connect(db_path)
            conn.execute(
                "UPDATE alarm_silences SET silenced_until = ? WHERE alarm_key = ?",
                (expired_ts, alarm_key),
            )
            conn.commit()
            conn.close()

            active_silences = store.list_alarm_silences(include_expired=False)
            all_silences = store.list_alarm_silences(include_expired=True)
            self.assertNotIn(alarm_key, active_silences)
            self.assertIn(alarm_key, all_silences)

            store.clear_alarm_silence(alarm_key)
            self.assertEqual({}, store.list_alarm_silences(include_expired=True))

    def test_purge_expired_alarm_silences_deletes_only_expired_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "audit.db"
            store = AuditStore(str(db_path))

            expired_key = "ALARM severity=high type=command-failure-streak device=10.0.0.1 threshold=2"
            active_key = "ALARM severity=critical type=offline-streak device=10.0.0.2 threshold=2"
            store.silence_alarm(expired_key, "alice:admin", 10)
            store.silence_alarm(active_key, "alice:admin", 10)

            expired_ts = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
            active_ts = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
            conn = sqlite3.connect(db_path)
            conn.execute(
                "UPDATE alarm_silences SET silenced_until = ? WHERE alarm_key = ?",
                (expired_ts, expired_key),
            )
            conn.execute(
                "UPDATE alarm_silences SET silenced_until = ? WHERE alarm_key = ?",
                (active_ts, active_key),
            )
            conn.commit()
            conn.close()

            deleted = store.purge_expired_alarm_silences()
            self.assertEqual(1, deleted)

            remaining = store.list_alarm_silences(include_expired=True)
            self.assertNotIn(expired_key, remaining)
            self.assertIn(active_key, remaining)

    def test_alarm_event_history_records_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "audit.db"
            store = AuditStore(str(db_path))

            alarm_key = "ALARM severity=critical type=offline-streak device=10.0.0.1 threshold=2"
            store.acknowledge_alarm(alarm_key, "alice:admin", "ack")
            store.clear_alarm_acknowledgement_with_actor(alarm_key, "alice:admin", "clear ack")
            store.silence_alarm(alarm_key, "alice:admin", 5, "silence")
            store.clear_alarm_silence_with_actor(alarm_key, "alice:admin", "clear silence")

            events = store.list_alarm_events(limit=10)

        self.assertGreaterEqual(len(events), 4)
        self.assertEqual("clear_silence", events[0]["action"])
        self.assertEqual("silence", events[1]["action"])
        self.assertEqual("clear_acknowledgement", events[2]["action"])
        self.assertEqual("acknowledge", events[3]["action"])

    def test_purge_old_alarm_events_and_table_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "audit.db"
            store = AuditStore(str(db_path))

            old_key = "ALARM severity=high type=command-failure-streak device=10.0.0.1 threshold=2"
            new_key = "ALARM severity=critical type=offline-streak device=10.0.0.2 threshold=2"
            store.log_alarm_event(old_key, "acknowledge", "alice:admin", "old")
            store.log_alarm_event(new_key, "acknowledge", "alice:admin", "new")

            old_ts = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
            conn = sqlite3.connect(db_path)
            conn.execute(
                "UPDATE alarm_events SET timestamp = ? WHERE alarm_key = ?",
                (old_ts, old_key),
            )
            conn.commit()
            conn.close()

            deleted = store.purge_old_alarm_events(retention_days=30)
            counts = store.table_row_counts()

        self.assertEqual(1, deleted)
        self.assertIn("alarm_events", counts)
        self.assertEqual(1, counts["alarm_events"])

    def test_alert_webhook_queue_and_deadletter_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "audit.db"
            store = AuditStore(str(db_path))

            payload = {"alert": "storage alert: alarm_events"}
            queued = store.enqueue_alert_webhook("alert-key-1", payload)
            self.assertTrue(queued)

            items = store.list_alert_webhook_queue(limit=10)
            self.assertEqual(1, len(items))
            queue_id = int(items[0]["id"])

            moved = store.record_alert_webhook_failure(queue_id, max_attempts=1, error="failed")
            self.assertTrue(moved)
            self.assertEqual(0, len(store.list_alert_webhook_queue(limit=10)))
            self.assertEqual(1, len(store.list_alert_webhook_deadletter(limit=10)))


if __name__ == "__main__":
    unittest.main()
