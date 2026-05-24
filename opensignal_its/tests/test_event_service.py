import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from opensignal_its.db.audit_store import AuditStore, CommandAuditRecord
from opensignal_its.services import event_service


class EventServiceTests(unittest.TestCase):
    def setUp(self):
        self._env = {
            "OPENSIGNAL_ALARM_OFFLINE_SNAPSHOT_STREAK": os.environ.get("OPENSIGNAL_ALARM_OFFLINE_SNAPSHOT_STREAK"),
            "OPENSIGNAL_ALARM_COMMAND_FAILURE_STREAK": os.environ.get("OPENSIGNAL_ALARM_COMMAND_FAILURE_STREAK"),
            "OPENSIGNAL_ALARM_SILENCE_DEFAULT_MINUTES": os.environ.get("OPENSIGNAL_ALARM_SILENCE_DEFAULT_MINUTES"),
            "OPENSIGNAL_ALARM_SILENCE_CRITICAL_MINUTES": os.environ.get("OPENSIGNAL_ALARM_SILENCE_CRITICAL_MINUTES"),
            "OPENSIGNAL_ALARM_SILENCE_HIGH_MINUTES": os.environ.get("OPENSIGNAL_ALARM_SILENCE_HIGH_MINUTES"),
            "OPENSIGNAL_ALARM_SILENCE_OFFLINE_STREAK_MINUTES": os.environ.get("OPENSIGNAL_ALARM_SILENCE_OFFLINE_STREAK_MINUTES"),
            "OPENSIGNAL_ALARM_SILENCE_COMMAND_FAILURE_STREAK_MINUTES": os.environ.get("OPENSIGNAL_ALARM_SILENCE_COMMAND_FAILURE_STREAK_MINUTES"),
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

                payload = event_service.EventService.build_timeline_and_alarms(50, 50, None)
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

                payload = event_service.EventService.build_timeline_and_alarms(50, 50, None)
            finally:
                event_service.STORE = original_store

        self.assertEqual([], payload["alarms"])

    def test_acknowledge_and_clear_alarm(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = AuditStore(str(Path(tmp) / "audit.db"))
            original_store = event_service.STORE
            event_service.STORE = store
            try:
                alarm_key = "ALARM severity=critical type=offline-streak device=10.0.0.1 threshold=2"
                ok, msg = event_service.EventService.acknowledge_alarm(
                    alarm_key=alarm_key,
                    actor="alice:admin",
                    note="Investigating",
                )
                self.assertTrue(ok)
                self.assertIn("acknowledged", msg)

                acks = store.list_alarm_acknowledgements()
                self.assertIn(alarm_key, acks)

                ok, msg = event_service.EventService.clear_alarm_acknowledgement(
                    alarm_key=alarm_key
                )
                self.assertTrue(ok)
                self.assertIn("cleared", msg)

                acks = store.list_alarm_acknowledgements()
                self.assertEqual({}, acks)
            finally:
                event_service.STORE = original_store

    def test_window_minutes_filters_old_activity(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = AuditStore(str(Path(tmp) / "audit.db"))
            original_store = event_service.STORE
            event_service.STORE = store
            try:
                now = datetime.now(timezone.utc)
                old_ts = (now - timedelta(hours=2)).isoformat()
                recent_ts = (now - timedelta(minutes=10)).isoformat()

                store.log_status_snapshot(
                    device_ip="10.0.0.1",
                    payload={"timestamp": old_ts, "is_online": True, "status_text": "old"},
                )
                store.log_status_snapshot(
                    device_ip="10.0.0.1",
                    payload={"timestamp": recent_ts, "is_online": True, "status_text": "recent"},
                )

                payload = event_service.EventService.build_timeline_and_alarms(
                    command_limit=50,
                    snapshot_limit=50,
                    window_minutes=15,
                )
            finally:
                event_service.STORE = original_store

        timeline = "\n".join(payload["timeline"])
        self.assertIn("status=recent", timeline)
        self.assertNotIn("status=old", timeline)

    def test_alarm_severity_priority_orders_offline_before_command_fail(self):
        os.environ["OPENSIGNAL_ALARM_OFFLINE_SNAPSHOT_STREAK"] = "2"
        os.environ["OPENSIGNAL_ALARM_COMMAND_FAILURE_STREAK"] = "2"

        with tempfile.TemporaryDirectory() as tmp:
            store = AuditStore(str(Path(tmp) / "audit.db"))
            original_store = event_service.STORE
            event_service.STORE = store
            try:
                store.log_status_snapshot(
                    device_ip="10.0.0.10",
                    payload={"timestamp": "2026-01-01T00:00:00+00:00", "is_online": False, "status_text": "offline"},
                )
                store.log_status_snapshot(
                    device_ip="10.0.0.10",
                    payload={"timestamp": "2026-01-01T00:01:00+00:00", "is_online": False, "status_text": "offline"},
                )

                store.log_command(
                    CommandAuditRecord(
                        timestamp="2026-01-01T00:02:00+00:00",
                        correlation_id="c10",
                        device_ip="10.0.0.20",
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
                        correlation_id="c11",
                        device_ip="10.0.0.20",
                        command_type="set_mode",
                        command_value={"mode": "free"},
                        probe_only=False,
                        allowed=True,
                        success=False,
                        error="failed",
                        actor="alice:admin",
                    )
                )

                payload = event_service.EventService.build_timeline_and_alarms(50, 50, None)
            finally:
                event_service.STORE = original_store

        self.assertGreaterEqual(len(payload["alarms"]), 2)
        self.assertIn("severity=critical", payload["alarms"][0])

    def test_silenced_alarm_moves_from_active_to_silenced_rows(self):
        os.environ["OPENSIGNAL_ALARM_OFFLINE_SNAPSHOT_STREAK"] = "2"

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
                    "device=10.0.0.99 threshold=2"
                )
                store.silence_alarm(alarm_key, "alice:admin", 15, "maintenance")

                payload = event_service.EventService.build_timeline_and_alarms(50, 50, None)
            finally:
                event_service.STORE = original_store

        self.assertNotIn(alarm_key, payload["alarms"])
        self.assertTrue(any(alarm_key in row for row in payload["silenced_alarms"]))

    def test_recommended_silence_minutes_prefers_type_over_severity(self):
        os.environ["OPENSIGNAL_ALARM_SILENCE_CRITICAL_MINUTES"] = "9"
        os.environ["OPENSIGNAL_ALARM_SILENCE_OFFLINE_STREAK_MINUTES"] = "13"

        alarm_key = "ALARM severity=critical type=offline-streak device=10.0.0.1 threshold=2"
        minutes = event_service.EventService.recommended_silence_minutes(alarm_key)
        self.assertEqual(13, minutes)

    def test_recommended_silence_minutes_falls_back_to_defaults(self):
        os.environ["OPENSIGNAL_ALARM_SILENCE_DEFAULT_MINUTES"] = "41"

        self.assertEqual(41, event_service.EventService.recommended_silence_minutes(""))
        self.assertEqual(
            41,
            event_service.EventService.recommended_silence_minutes(
                "ALARM severity=medium type=other device=10.0.0.1"
            ),
        )

    def test_list_alarm_history_rows_returns_recent_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = AuditStore(str(Path(tmp) / "audit.db"))
            original_store = event_service.STORE
            event_service.STORE = store
            try:
                alarm_key = "ALARM severity=critical type=offline-streak device=10.0.0.1 threshold=2"
                event_service.EventService.acknowledge_alarm(alarm_key, "alice:admin", "ack")
                event_service.EventService.clear_alarm_acknowledgement_with_actor(
                    alarm_key,
                    actor="alice:admin",
                    note="clear ack",
                )
                rows = event_service.EventService.list_alarm_history_rows(limit=10)
            finally:
                event_service.STORE = original_store

        self.assertGreaterEqual(len(rows), 2)
        self.assertIn("ALARM_EVENT", rows[0])
        self.assertIn("actor=alice:admin", rows[0])

    def test_list_alarm_history_rows_applies_filters_and_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = AuditStore(str(Path(tmp) / "audit.db"))
            original_store = event_service.STORE
            event_service.STORE = store
            try:
                key_a = "ALARM severity=critical type=offline-streak device=10.0.0.1 threshold=2"
                key_b = "ALARM severity=high type=command-failure-streak device=10.0.0.2 threshold=2"
                event_service.EventService.acknowledge_alarm(key_a, "alice:admin", "ack-a")
                event_service.EventService.silence_alarm(key_a, "alice:admin", 10, "sil-a")
                event_service.EventService.acknowledge_alarm(key_b, "bob:admin", "ack-b")

                rows = event_service.EventService.list_alarm_history_rows(
                    limit=1,
                    action_filter="acknowledge",
                    actor_contains="bob",
                    key_contains="10.0.0.2",
                )
            finally:
                event_service.STORE = original_store

        self.assertEqual(1, len(rows))
        self.assertIn("ALARM_EVENT acknowledge", rows[0])
        self.assertIn("actor=bob:admin", rows[0])

    def test_build_display_view_structures_alarm_and_timeline_rows(self):
        payload = {
            "timeline": [
                (
                    "[2026-01-01T00:03:00+00:00] CMD 10.0.0.1 set_mode "
                    "actor=alice:admin ALLOWED FAIL error=failed hard"
                ),
                "[2026-01-01T00:04:00+00:00] SNAP 10.0.0.2 poll ONLINE status=Pattern 2 | Unit Free",
            ],
            "alarms": [
                "ALARM severity=critical type=offline-streak device=10.0.0.1 threshold=2"
            ],
            "acknowledged_alarms": [
                (
                    "ALARM severity=high type=command-failure-streak device=10.0.0.2 threshold=3 "
                    "[ACK by bob:admin at 2026-01-01T00:10:00+00:00]"
                )
            ],
            "silenced_alarms": [
                (
                    "ALARM severity=critical type=offline-streak device=10.0.0.3 threshold=2 "
                    "[SILENCED by alice:admin until 2026-01-01T00:15:00+00:00]"
                )
            ],
        }

        view = event_service.EventService.build_display_view(payload)

        self.assertEqual("Command", view.timeline[0].kind_label)
        self.assertEqual("10.0.0.1", view.timeline[0].device_ip)
        self.assertEqual("Fail", view.timeline[0].status_label)
        self.assertIn("Actor alice:admin", view.timeline[0].detail)
        self.assertIn("Error failed hard", view.timeline[0].detail)

        self.assertEqual("Snapshot", view.timeline[1].kind_label)
        self.assertEqual("Online", view.timeline[1].status_label)
        self.assertIn("Pattern 2 | Unit Free", view.timeline[1].detail)

        self.assertEqual("Offline Streak", view.alarms[0].summary)
        self.assertEqual("Critical", view.alarms[0].severity_label)
        self.assertEqual("Active", view.alarms[0].state_label)
        self.assertEqual("Threshold 2", view.alarms[0].detail)

        self.assertEqual("Acknowledged", view.acknowledged_alarms[0].state_label)
        self.assertIn("ACK by bob:admin", view.acknowledged_alarms[0].state_detail)

        self.assertEqual("Silenced", view.silenced_alarms[0].state_label)
        self.assertIn("SILENCED by alice:admin", view.silenced_alarms[0].state_detail)


if __name__ == "__main__":
    unittest.main()
