import asyncio
import unittest
from unittest.mock import patch

import reflex as rx

from opensignal_its.models.event import AlarmDisplayRow, EventDisplayView, TimelineDisplayRow
from opensignal_its.models.fleet import FleetDeviceStatus, FleetRefreshView, RuntimeRegistryView
from opensignal_its.states.auth_state import AuthStateMixin
from opensignal_its.states.audit_state import AuditStateMixin
from opensignal_its.states.command_state import CommandStateMixin
from opensignal_its.states.configuration_state import ConfigurationStateMixin
from opensignal_its.states.event_state import _event_view_to_state_fields
from opensignal_its.states.fleet_state import FleetStateMixin, _fleet_view_to_state_fields
from opensignal_its.states.maintenance_state import _runtime_health_snapshot_to_state_fields
from opensignal_its.states.monitor_state import MonitorStateMixin
from opensignal_its.states.polling_state import _runtime_registry_view_to_state_fields
from opensignal_its.states.safety_state import SafetyStateMixin
from opensignal_its.states.time_state import TimeStateMixin
from opensignal_its.states.traffic_state import TrafficState
from opensignal_its.states.workspace_state import WorkspaceStateMixin


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
        self.assertEqual(1, len(adapted["fleet_status_cards"]))
        self.assertEqual("int-1", adapted["fleet_status_cards"][0]["device_id"])
        self.assertEqual("Online", adapted["fleet_status_cards"][0]["status_label"])
        self.assertTrue(bool(adapted["selected_payload"]))
        self.assertEqual(1, int(adapted["selected_mp_model"]))

    def test_fleet_view_to_state_fields_handles_empty_view(self):
        view = FleetRefreshView()

        adapted = _fleet_view_to_state_fields(view)

        self.assertEqual("", adapted["selected_device_id"])
        self.assertEqual([], adapted["fleet_device_rows"])
        self.assertEqual({}, adapted["fleet_status_by_id"])
        self.assertEqual([], adapted["fleet_status_cards"])
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
        class _SafetyProbe(SafetyStateMixin, rx.State):
            write_unlock_seconds_text: str = "120"

        probe = _SafetyProbe(_reflex_internal_init=True)
        probe.write_unlock_seconds_text = "5"
        self.assertEqual(15, probe._write_unlock_seconds())

        probe.write_unlock_seconds_text = "bad"
        self.assertEqual(120, probe._write_unlock_seconds())

    def test_configuration_state_sync_controller_profile_rows_builds_notice_and_rows(self):
        class _ConfigurationProbe(ConfigurationStateMixin, rx.State):
            device_profiles_json: str = """[
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
            controller_profile_filter_text: str = ""
            controller_profile_sort_key: str = "device_id"
            controller_profile_sort_desc: bool = False
            fleet_status_by_id: dict[str, object] = {}

        probe = _ConfigurationProbe(_reflex_internal_init=True)

        profiles = probe._sync_controller_profile_rows()

        self.assertEqual(1, len(profiles))
        self.assertEqual(1, len(probe.controller_profile_rows))
        self.assertIn("1 controller profile configured.", probe.controller_profile_notice)

    def test_configuration_state_sync_controller_profile_rows_applies_mapping_filter(self):
        class _ConfigurationProbe(ConfigurationStateMixin, rx.State):
            device_profiles_json: str = """[
                {
                    "device_id": "int-1",
                    "device_type": "siemens_m60",
                    "ip_address": "10.0.0.1",
                    "latitude": 40.7128,
                    "longitude": -74.0060
                },
                {
                    "device_id": "int-2",
                    "device_type": "siemens_m60",
                    "ip_address": "10.0.0.2"
                }
            ]"""
            controller_profile_filter_text: str = ""
            controller_profile_mapping_filter: str = "unmapped"
            controller_profile_sort_key: str = "device_id"
            controller_profile_sort_desc: bool = False
            fleet_status_by_id: dict[str, object] = {}

        probe = _ConfigurationProbe(_reflex_internal_init=True)

        probe._sync_controller_profile_rows()

        self.assertEqual(["int-2"], [row["device_id"] for row in probe.controller_profile_rows])
        self.assertIn("Showing 1 of 2 controller profiles.", probe.controller_profile_notice)

    def test_fleet_state_refresh_fleet_card_fields_applies_mapping_filter(self):
        class _FleetProbe(FleetStateMixin, rx.State):
            device_profiles_json: str = """[
                {
                    "device_id": "int-1",
                    "device_type": "siemens_m60",
                    "ip_address": "10.0.0.1",
                    "latitude": 40.7128,
                    "longitude": -74.0060
                },
                {
                    "device_id": "int-2",
                    "device_type": "siemens_m60",
                    "ip_address": "10.0.0.2"
                }
            ]"""
            fleet_status_by_id: dict[str, object] = {}
            fleet_status_mapping_filter: str = "unmapped"

        probe = _FleetProbe(_reflex_internal_init=True)

        probe._refresh_fleet_card_fields()

        self.assertEqual(["int-2"], [row["device_id"] for row in probe.fleet_status_cards])
        self.assertEqual("Showing 1 controller needing coordinates.", probe.fleet_status_card_notice)

    def test_monitor_state_build_config_normalizes_input(self):
        class _MonitorProbe(MonitorStateMixin, rx.State):
            ip_address: str = "166.156.88.223"
            port_text: str = "161"
            community: str = "public"
            snmp_version: str = "auto"
            timeout_text: str = "3"
            retries_text: str = "1"

        probe = _MonitorProbe(_reflex_internal_init=True)
        probe.ip_address = " 10.0.0.8 "
        probe.port_text = "2161"
        probe.community = " public-ro "
        probe.snmp_version = " V1 "
        probe.timeout_text = "4.5"
        probe.retries_text = "2"

        config = probe._build_config()

        self.assertEqual("10.0.0.8", config.ip_address)
        self.assertEqual(2161, config.port)
        self.assertEqual("public-ro", config.community)
        self.assertEqual("v1", config.snmp_version)
        self.assertEqual(4.5, config.timeout_seconds)
        self.assertEqual(2, config.retries)

    def test_command_state_select_pattern_wrapper_delegates_to_send_command(self):
        class _CommandProbe(CommandStateMixin, rx.State):
            calls: list[tuple[object, object, object]] = []

            async def send_command(self, cmd_type, value, force_confirmed=False):
                self.calls.append((cmd_type, value, force_confirmed))

        probe = _CommandProbe(_reflex_internal_init=True)
        probe.calls = []

        asyncio.run(probe.select_pattern_1())

        self.assertEqual([("select_pattern", 1, False)], probe.calls)

    def test_fleet_state_interval_helpers_apply_bounds_and_fallbacks(self):
        class _FleetProbe(FleetStateMixin, rx.State):
            refresh_interval_text: str = "5"
            reconnect_interval_text: str = "10"

        probe = _FleetProbe(_reflex_internal_init=True)
        probe.refresh_interval_text = "0"
        self.assertEqual(1.0, probe._refresh_interval_seconds())

        probe.refresh_interval_text = "bad"
        self.assertEqual(5.0, probe._refresh_interval_seconds())

        probe.reconnect_interval_text = "1"
        self.assertEqual(2.0, probe._reconnect_interval_seconds())

        probe.reconnect_interval_text = "bad"
        self.assertEqual(10.0, probe._reconnect_interval_seconds())

    def test_audit_state_export_requires_admin_authorization(self):
        class _AuditProbe(AuditStateMixin, rx.State):
            error: str = ""

            def _is_role_authorized(self, allowed_roles):
                return False

        probe = _AuditProbe(_reflex_internal_init=True)

        probe.export_audit_report()

        self.assertEqual("Audit export denied: admin authentication required.", probe.audit_export_notice)
        self.assertEqual(probe.audit_export_notice, probe.error)

    def test_time_state_helpers_parse_deltas_and_expiration(self):
        class _TimeProbe(TimeStateMixin, rx.State):
            pass

        probe = _TimeProbe(_reflex_internal_init=True)

        self.assertIsNone(probe._parse_timestamp("not-a-timestamp"))
        self.assertEqual(5, probe._poll_delta_seconds("2026-05-23T00:00:00+00:00", "2026-05-23T00:00:05+00:00"))
        self.assertTrue(probe._has_expired("2000-01-01T00:00:00+00:00"))
        self.assertFalse(probe._has_expired("2999-01-01T00:00:00+00:00"))
        self.assertFalse(probe._has_expired(probe._utc_future_iso(60)))

    def test_workspace_state_updates_mode_and_syncs_configuration(self):
        class _WorkspaceProbe(WorkspaceStateMixin, rx.State):
            synced: bool = False

            def _sync_controller_profile_rows(self):
                self.synced = True

        probe = _WorkspaceProbe(_reflex_internal_init=True)

        probe.update_ui_workspace_mode("configuration")

        self.assertEqual("configuration", probe.ui_workspace_mode)
        self.assertTrue(probe.synced)


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
            "controller_profile_mapping_filter",
            "controller_profile_sort_key",
            "controller_profile_sort_desc",
            "controller_profile_form_error",
            "controller_profile_original_device_id",
            "controller_profile_form_device_id",
            "controller_profile_form_name",
            "controller_profile_form_location_name",
            "controller_profile_form_device_type",
            "controller_profile_form_ip_address",
            "controller_profile_form_port_text",
            "controller_profile_form_community",
            "controller_profile_form_snmp_version",
            "controller_profile_form_timeout_text",
            "controller_profile_form_retries_text",
            "controller_profile_form_latitude_text",
            "controller_profile_form_longitude_text",
            "update_device_profiles_json",
            "update_controller_profile_filter_text",
            "update_controller_profile_mapping_filter",
            "update_controller_profile_sort_key",
            "toggle_controller_profile_sort_direction",
            "update_controller_profile_form_device_id",
            "update_controller_profile_form_name",
            "update_controller_profile_form_location_name",
            "update_controller_profile_form_device_type",
            "update_controller_profile_form_ip_address",
            "update_controller_profile_form_port_text",
            "update_controller_profile_form_community",
            "update_controller_profile_form_snmp_version",
            "update_controller_profile_form_timeout_text",
            "update_controller_profile_form_retries_text",
            "update_controller_profile_form_latitude_text",
            "update_controller_profile_form_longitude_text",
            "new_controller_profile",
            "load_controller_profile",
            "load_controller_profile_from_row",
            "save_controller_profile",
            "delete_controller_profile",
            "open_selected_controller_status",
        ]

        missing = [name for name in required if not hasattr(TrafficState, name)]

        self.assertEqual([], missing)

    def test_traffic_state_exposes_monitor_state_members(self):
        required = [
            "m60_status",
            "m60_status_json",
            "status_text",
            "active_snmp_version",
            "current_pattern",
            "unit_status",
            "ring_status_summary",
            "phase_data",
            "is_online",
            "last_updated",
            "ip_address",
            "port_text",
            "community",
            "snmp_version",
            "timeout_text",
            "retries_text",
            "selected_device_id",
            "monitor_detail_tab",
            "monitor_view",
            "update_ip_address",
            "update_port_text",
            "update_community",
            "update_snmp_version",
            "update_selected_device_id",
            "update_timeout_text",
            "update_retries_text",
            "update_monitor_detail_tab",
            "update_monitor_view",
            "open_intersection_detail",
            "back_to_dashboard",
            "select_controller_from_row",
            "select_controller_from_map_points",
            "_build_config",
            "_selected_device_target",
            "_apply_phase_payload",
            "_collect_selected_status_snapshot",
            "_apply_status_snapshot",
            "add_and_poll_m60",
            "connect_m60",
            "refresh_status",
            "connect_and_start_polling",
        ]

        missing = [name for name in required if not hasattr(TrafficState, name)]

        self.assertEqual([], missing)

    def test_traffic_state_exposes_command_state_members(self):
        required = [
            "_safe_log_command",
            "send_command",
            "select_pattern_1",
            "select_pattern_2",
            "set_mode_free",
            "set_mode_coordinated",
            "manual_hold",
            "advance_phase",
        ]

        missing = [name for name in required if not hasattr(TrafficState, name)]

        self.assertEqual([], missing)

    def test_traffic_state_exposes_fleet_state_members(self):
        required = [
            "fleet_status_summary",
            "fleet_device_rows",
            "fleet_status_by_id",
            "fleet_status_cards",
            "fleet_status_mapping_filter",
            "fleet_status_card_notice",
            "fleet_map_markers",
            "fleet_unmapped_device_ids",
            "fleet_map_data",
            "fleet_map_layout",
            "fleet_map_figure",
            "fleet_map_notice",
            "fleet_online_count",
            "fleet_offline_count",
            "fleet_total_count",
            "auto_refresh_enabled",
            "refresh_interval_text",
            "auto_reconnect_enabled",
            "reconnect_interval_text",
            "auto_refresh_running",
            "update_auto_refresh_enabled",
            "update_refresh_interval_text",
            "update_auto_reconnect_enabled",
            "update_reconnect_interval_text",
            "update_fleet_status_mapping_filter",
            "_refresh_interval_seconds",
            "_reconnect_interval_seconds",
            "_fleet_profiles",
            "_refresh_fleet_map_fields",
            "_refresh_fleet_aggregate_fields",
            "_cache_device_status",
            "refresh_fleet_status",
            "auto_refresh_loop",
        ]

        missing = [name for name in required if not hasattr(TrafficState, name)]

        self.assertEqual([], missing)

    def test_traffic_state_exposes_audit_state_members(self):
        required = [
            "audit_export_notice",
            "audit_export_path",
            "export_audit_report",
        ]

        missing = [name for name in required if not hasattr(TrafficState, name)]

        self.assertEqual([], missing)

    def test_traffic_state_exposes_time_state_members(self):
        required = [
            "_utc_now_iso",
            "_parse_timestamp",
            "_poll_delta_seconds",
            "_has_expired",
        ]

        missing = [name for name in required if not hasattr(TrafficState, name)]

        self.assertEqual([], missing)

    def test_traffic_state_exposes_workspace_state_members(self):
        required = [
            "ui_workspace_mode",
            "update_ui_workspace_mode",
        ]

        missing = [name for name in required if not hasattr(TrafficState, name)]

        self.assertEqual([], missing)

    def test_traffic_state_exposes_shell_fields(self):
        required = [
            "error",
            "is_loading",
        ]

        missing = [name for name in required if not hasattr(TrafficState, name)]

        self.assertEqual([], missing)

    def test_traffic_state_registers_inherited_mixin_vars(self):
        required = [
            "is_online",
            "alarm_rows",
            "safe_command_probe",
            "current_operator",
            "fleet_total_count",
            "ui_workspace_mode",
        ]

        missing = [name for name in required if name not in TrafficState.vars]

        self.assertEqual([], missing)


if __name__ == "__main__":
    unittest.main()
