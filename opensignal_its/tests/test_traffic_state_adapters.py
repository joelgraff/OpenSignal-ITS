import unittest
from unittest.mock import patch

from opensignal_its.models.event import AlarmDisplayRow, EventDisplayView, TimelineDisplayRow
from opensignal_its.models.fleet import FleetDeviceStatus, FleetRefreshView, RuntimeRegistryView
from opensignal_its.states.auth_state import AuthStateMixin
from opensignal_its.states.configuration_state import ConfigurationStateMixin
from opensignal_its.states.event_state import _event_view_to_state_fields
from opensignal_its.states.maintenance_state import _runtime_health_snapshot_to_state_fields
from opensignal_its.states.polling_state import _runtime_registry_view_to_state_fields
from opensignal_its.states.safety_state import SafetyStateMixin
from opensignal_its.states.traffic_state import TrafficState, _fleet_view_to_state_fields


class TrafficStateAdapterTests(unittest.TestCase):
    def test_fleet_view_to_state_fields_maps_core_values(self):
        view = FleetRefreshView(
            rows=["int-1 [siemens_m60] ONLINE - ok"],
            status_by_id={
                "int-1": FleetDeviceStatus(
                    device_type="siemens_m60",
                    is_online=True,
                    status_text="ok",
                    timestamp="2026-05-23T00:00:00+00:00",
                )
            },
            selected_payload={"is_online": True, "status_text": "ok"},
            selected_mp_model=1,
            selected_device_type="siemens_m60",
            selected_device_id="int-1",
        )

        adapted = _fleet_view_to_state_fields(view)

        self.assertEqual("int-1", adapted["selected_device_id"])
        self.assertEqual(["int-1 [siemens_m60] ONLINE - ok"], adapted["fleet_device_rows"])
        self.assertIn("int-1", adapted["fleet_status_by_id"])
        self.assertTrue(bool(adapted["selected_payload"]))
        self.assertEqual(1, int(adapted["selected_mp_model"]))

    def test_fleet_view_to_state_fields_handles_empty_view(self):
        view = FleetRefreshView()

        adapted = _fleet_view_to_state_fields(view)

        self.assertEqual("", adapted["selected_device_id"])
        self.assertEqual([], adapted["fleet_device_rows"])
        self.assertEqual({}, adapted["fleet_status_by_id"])
        self.assertIsNone(adapted["selected_payload"])
        self.assertEqual(1, int(adapted["selected_mp_model"]))
        self.assertEqual("siemens_m60", adapted["selected_device_type"])

    def test_event_view_to_state_fields_maps_event_rows(self):
        view = EventDisplayView(
            timeline=[
                TimelineDisplayRow(
                    timestamp="2026-05-23T00:00:00+00:00",
                    kind="snapshot",
                    kind_label="Snapshot",
                    kind_scheme="gray",
                    device_ip="10.0.0.1",
                    summary="Status Snapshot",
                    detail="Poll | Online",
                    status_label="Online",
                    status_scheme="green",
                )
            ],
            alarms=[
                AlarmDisplayRow(
                    alarm_key="ALARM severity=critical type=offline-streak device=10.0.0.1 threshold=2",
                    severity="critical",
                    severity_label="Critical",
                    severity_scheme="red",
                    alarm_type="offline-streak",
                    summary="Offline Streak",
                    device_ip="10.0.0.1",
                    detail="Threshold 2",
                    state_label="Active",
                    state_scheme="orange",
                )
            ],
        )

        adapted = _event_view_to_state_fields(view)

        self.assertEqual("Snapshot", adapted["event_timeline_rows"][0]["kind_label"])
        self.assertEqual("10.0.0.1", adapted["event_timeline_rows"][0]["device_ip"])
        self.assertEqual("Offline Streak", adapted["alarm_rows"][0]["summary"])
        self.assertEqual([], adapted["acknowledged_alarm_rows"])
        self.assertEqual([], adapted["silenced_alarm_rows"])

    def test_runtime_registry_view_to_state_fields_maps_summary_and_rows(self):
        view = RuntimeRegistryView(
            summary="Active poll sessions: 2 sites, 1 polling loops running.",
            rows=["siemens_m60::a", "siemens_m60::b (polling)"],
            count=2,
            running_count=1,
        )

        adapted = _runtime_registry_view_to_state_fields(view)

        self.assertEqual(
            "Active poll sessions: 2 sites, 1 polling loops running.",
            adapted["runtime_registry_summary"],
        )
        self.assertEqual(["siemens_m60::a", "siemens_m60::b (polling)"], adapted["runtime_registry_rows"])

    def test_runtime_health_snapshot_to_state_fields_maps_runtime_health(self):
        adapted = _runtime_health_snapshot_to_state_fields(
            {
                "enabled": True,
                "running": False,
                "interval_seconds": 300,
                "error": "clock drift",
            },
            {
                "last_run_at": "2026-05-23T00:00:00+00:00",
                "message": "Retention cleanup complete.",
            },
            {
                "storage": {
                    "table_row_counts": {"command_audit": 4, "status_snapshots": 9},
                    "warnings": ["storage warning: command_audit high"],
                    "persistent_alerts": ["storage alert: command_audit persisted"],
                    "alert_dispatch": {
                        "enabled": True,
                        "sent": 1,
                        "skipped": 2,
                        "failed": 3,
                        "deadlettered": 4,
                    },
                }
            },
        )

        self.assertTrue(adapted["retention_scheduler_enabled"])
        self.assertFalse(adapted["retention_scheduler_running"])
        self.assertEqual("300", adapted["retention_scheduler_interval_text"])
        self.assertEqual("clock drift", adapted["retention_scheduler_error"])
        self.assertEqual(["storage warning: command_audit high"], adapted["runtime_storage_warning_rows"])
        self.assertEqual(["storage alert: command_audit persisted"], adapted["runtime_storage_alert_rows"])
        self.assertIn("enabled=True", adapted["runtime_alert_dispatch_summary"])
        self.assertIn("command_audit=4", adapted["runtime_storage_summary"])
        self.assertIn("Scheduler: enabled, stopped, interval=300s", adapted["runtime_health_notice"])

    def test_auth_state_static_limits_apply_bounds_and_fallbacks(self):
        with patch.dict(
            "os.environ",
            {
                "OPENSIGNAL_MAX_LOGIN_ATTEMPTS": "0",
                "OPENSIGNAL_LOGIN_LOCKOUT_SECONDS": "bad",
            },
            clear=False,
        ):
            self.assertEqual(1, AuthStateMixin._max_login_attempts())
            self.assertEqual(300, AuthStateMixin._login_lockout_seconds())

    def test_safety_state_write_unlock_seconds_applies_bounds_and_fallbacks(self):
        class _SafetyProbe(SafetyStateMixin):
            write_unlock_seconds_text = "120"

        probe = _SafetyProbe()
        probe.write_unlock_seconds_text = "5"
        self.assertEqual(15, probe._write_unlock_seconds())

        probe.write_unlock_seconds_text = "bad"
        self.assertEqual(120, probe._write_unlock_seconds())

    def test_configuration_state_sync_controller_profile_rows_builds_notice_and_rows(self):
        class _ConfigurationProbe(ConfigurationStateMixin):
            device_profiles_json = """[
                {
                    "device_id": "int-1",
                    "name": "Main & 1st",
                    "device_type": "siemens_m60",
                    "ip_address": "10.0.0.1",
                    "port": 161,
                    "community": "public",
                    "snmp_version": "auto",
                    "timeout_seconds": 3.0,
                    "retries": 1
                }
            ]"""
            controller_profile_filter_text = ""
            controller_profile_sort_key = "device_id"
            controller_profile_sort_desc = False
            fleet_status_by_id = {}

        probe = _ConfigurationProbe()

        profiles = probe._sync_controller_profile_rows()

        self.assertEqual(1, len(profiles))
        self.assertEqual(1, len(probe.controller_profile_rows))
        self.assertIn("1 controller profile configured.", probe.controller_profile_notice)


    def test_traffic_state_exposes_event_state_members(self):
        required = [
            "event_notice",
            "event_window",
            "event_timeline_rows",
            "alarm_rows",
            "alarm_history_rows",
            "selected_alarm_key",
            "refresh_events_and_alarms",
            "acknowledge_selected_alarm",
            "apply_selected_alarm_silence_policy",
            "update_alarm_history_action_filter",
        ]

        missing = [name for name in required if not hasattr(TrafficState, name)]

        self.assertEqual([], missing)

    def test_traffic_state_exposes_polling_state_members(self):
        required = [
            "managed_polling_interval_text",
            "managed_polling_notice",
            "runtime_registry_summary",
            "runtime_registry_rows",
            "refresh_runtime_registry_status",
            "start_selected_managed_polling",
            "start_fleet_managed_polling",
            "stop_selected_managed_polling",
            "stop_fleet_managed_polling",
            "update_managed_polling_interval_text",
        ]

        missing = [name for name in required if not hasattr(TrafficState, name)]

        self.assertEqual([], missing)

    def test_traffic_state_exposes_maintenance_state_members(self):
        required = [
            "maintenance_notice",
            "runtime_health_notice",
            "runtime_storage_summary",
            "runtime_storage_warning_rows",
            "runtime_storage_alert_rows",
            "runtime_alert_dispatch_summary",
            "retention_scheduler_enabled",
            "retention_scheduler_running",
            "retention_scheduler_interval_text",
            "retention_scheduler_error",
            "last_retention_cleanup_at",
            "last_retention_cleanup_result",
            "run_retention_cleanup",
            "refresh_runtime_health",
        ]

        missing = [name for name in required if not hasattr(TrafficState, name)]

        self.assertEqual([], missing)

    def test_traffic_state_exposes_auth_state_members(self):
        required = [
            "login_username_input",
            "login_password_input",
            "is_authenticated",
            "current_operator",
            "current_role",
            "auth_notice",
            "failed_login_attempts",
            "login_lockout_until",
            "admin_recovery_key_input",
            "admin_recovery_notice",
            "update_login_username_input",
            "update_login_password_input",
            "update_admin_recovery_key_input",
            "login_operator",
            "logout_operator",
            "reset_login_lockout",
            "_actor_name",
            "_is_role_authorized",
        ]

        missing = [name for name in required if not hasattr(TrafficState, name)]

        self.assertEqual([], missing)

    def test_traffic_state_exposes_safety_state_members(self):
        required = [
            "safe_command_probe",
            "operator_key_input",
            "write_unlock_seconds_text",
            "write_unlock_until",
            "write_mode_active",
            "safety_notice",
            "confirmation_input",
            "pending_confirmation_token",
            "pending_confirmation_expires",
            "pending_command_type",
            "pending_command_value_json",
            "pending_confirmation_notice",
            "update_safe_command_probe",
            "update_operator_key_input",
            "update_write_unlock_seconds_text",
            "update_confirmation_input",
            "unlock_write_mode",
            "lock_write_mode",
            "confirm_pending_command",
            "_requires_confirmation",
            "_start_command_confirmation",
        ]

        missing = [name for name in required if not hasattr(TrafficState, name)]

        self.assertEqual([], missing)

    def test_traffic_state_exposes_configuration_state_members(self):
        required = [
            "device_profiles_json",
            "controller_profile_rows",
            "controller_profile_notice",
            "controller_profile_filter_text",
            "controller_profile_sort_key",
            "controller_profile_sort_desc",
            "controller_profile_form_error",
            "controller_profile_original_device_id",
            "controller_profile_form_device_id",
            "controller_profile_form_name",
            "controller_profile_form_device_type",
            "controller_profile_form_ip_address",
            "controller_profile_form_port_text",
            "controller_profile_form_community",
            "controller_profile_form_snmp_version",
            "controller_profile_form_timeout_text",
            "controller_profile_form_retries_text",
            "update_device_profiles_json",
            "update_controller_profile_filter_text",
            "update_controller_profile_sort_key",
            "toggle_controller_profile_sort_direction",
            "update_controller_profile_form_device_id",
            "update_controller_profile_form_name",
            "update_controller_profile_form_device_type",
            "update_controller_profile_form_ip_address",
            "update_controller_profile_form_port_text",
            "update_controller_profile_form_community",
            "update_controller_profile_form_snmp_version",
            "update_controller_profile_form_timeout_text",
            "update_controller_profile_form_retries_text",
            "new_controller_profile",
            "load_controller_profile",
            "load_controller_profile_from_row",
            "save_controller_profile",
            "delete_controller_profile",
            "open_selected_controller_status",
        ]

        missing = [name for name in required if not hasattr(TrafficState, name)]

        self.assertEqual([], missing)


if __name__ == "__main__":
    unittest.main()
