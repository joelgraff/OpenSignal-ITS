import os
import tempfile
import unittest
from pathlib import Path

from opensignal_its.db.audit_store import AuditStore, CommandAuditRecord
from opensignal_its.services import event_service


class EventServiceTests(unittest.TestCase):
    def setUp(self):
        self._env = {
            "OPENSIGNAL_ALARM_OFFLINE_SNAPSHOT_STREAK": os.environ.get("OPENSIGNAL_ALARM_OFFLINE_SNAPSHOT_STREAK"),
            "OPENSIGNAL_ALARM_COMMAND_FAILURE_STREAK": os.environ.get("OPENSIGNAL_ALARM_COMMAND_FAILURE_STREAK"),
        }

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_build_timeline_and_alarms_detects_offline_and_fail_streaks(self):
        os.environ["OPENSIGNAL_ALARM_OFFLINE_SNAPSHOT_STREAK"] = "2"
        os.environ["OPENSIGNAL_ALARM_COMMAND_FAILURE_STREAK"] = "2"

        with tempfile.TemporaryDirectory() as tmp:
            store = AuditStore(str(Path(tmp) / "audit.db"))
            original_store = event_service.STORE
            event_service.STORE = store
            try:
                store.log_status_snapshot(
                    device_ip="10.0.0.1",
                    payload={"timestamp": "2026-01-01T00:00:00+00:00", "is_online": False, "status_text": "offline"},
                )
                store.log_status_snapshot(
                    device_ip="10.0.0.1",
                    payload={"timestamp": "2026-01-01T00:01:00+00:00", "is_online": False, "status_text": "offline"},
                )

                store.log_command(
                    CommandAuditRecord(
                        timestamp="2026-01-01T00:02:00+00:00",
                        correlation_id="c1",
                        device_ip="10.0.0.1",
                        command_type="set_mode",
                        command_value={"mode": "free"},
                        probe_only=False,
                        allowed=True,
                        success=False,
                        error="failed",
                        actor="alice:admin",
                    )
                )
                store.log_command(
                    CommandAuditRecord(
                        timestamp="2026-01-01T00:03:00+00:00",
                        correlation_id="c2",
                        device_ip="10.0.0.1",
                        command_type="set_mode",
                        command_value={"mode": "coordinated"},
                        probe_only=False,
                        allowed=True,
                        success=False,
                        error="failed",
                        actor="alice:admin",
                    )
                )

                payload = event_service.EventService.build_timeline_and_alarms(50, 50)
            finally:
                event_service.STORE = original_store

        self.assertGreaterEqual(len(payload["timeline"]), 4)
        joined = "\n".join(payload["alarms"])
        self.assertIn("offline-streak", joined)
        self.assertIn("command-failure-streak", joined)

    def test_build_timeline_and_alarms_returns_no_alarms_without_streak(self):
        os.environ["OPENSIGNAL_ALARM_OFFLINE_SNAPSHOT_STREAK"] = "3"
        os.environ["OPENSIGNAL_ALARM_COMMAND_FAILURE_STREAK"] = "3"

        with tempfile.TemporaryDirectory() as tmp:
            store = AuditStore(str(Path(tmp) / "audit.db"))
            original_store = event_service.STORE
            event_service.STORE = store
            try:
                store.log_status_snapshot(
                    device_ip="10.0.0.1",
                    payload={"timestamp": "2026-01-01T00:00:00+00:00", "is_online": False, "status_text": "offline"},
                )
                store.log_command(
                    CommandAuditRecord(
                        timestamp="2026-01-01T00:02:00+00:00",
                        correlation_id="c1",
                        device_ip="10.0.0.1",
                        command_type="set_mode",
                        command_value={"mode": "free"},
                        probe_only=False,
                        allowed=True,
                        success=False,
                        error="failed",
                        actor="alice:admin",
                    )
                )

                payload = event_service.EventService.build_timeline_and_alarms(50, 50)
            finally:
                event_service.STORE = original_store

        self.assertEqual([], payload["alarms"])


if __name__ == "__main__":
    unittest.main()
