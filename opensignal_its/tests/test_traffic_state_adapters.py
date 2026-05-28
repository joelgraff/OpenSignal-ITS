import asyncio
import json
import unittest
from unittest.mock import patch

import reflex as rx

from opensignal_its.models.event import AlarmDisplayRow, EventDisplayView, TimelineDisplayRow
from opensignal_its.models.fleet import FleetDeviceStatus, FleetRefreshView, RuntimeRegistryView
from opensignal_its.models.media import MediaStreamStatus
from opensignal_its.services.command_service import CommandExecutionResult
from opensignal_its.states.auth_state import AuthStateMixin
from opensignal_its.states.audit_state import AuditStateMixin
from opensignal_its.states.command_state import CommandStateMixin
from opensignal_its.states.configuration_state import ConfigurationStateMixin
from opensignal_its.states.event_state import _event_view_to_state_fields
from opensignal_its.states.fleet_state import FleetStateMixin, _fleet_view_to_state_fields
from opensignal_its.states.maintenance_state import _runtime_health_snapshot_to_state_fields
from opensignal_its.states.monitor_state import MonitorStateMixin
from opensignal_its.states.polling_state import PollingStateMixin, _runtime_registry_view_to_state_fields
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

    def test_configuration_state_open_controller_profile_editor_switches_workspace_and_loads_profile(self):
        class _ConfigurationWorkspaceProbe(ConfigurationStateMixin, PollingStateMixin, WorkspaceStateMixin, rx.State):
            device_profiles_json: str = """[
                {
                    "device_id": "int-2",
                    "name": "Broadway",
                    "device_type": "siemens_m60",
                    "ip_address": "10.0.0.2",
                    "polling_enabled": false
                }
            ]"""
            controller_profile_filter_text: str = "downtown"
            controller_profile_mapping_filter: str = "unmapped"
            selected_device_id: str = ""
            fleet_status_by_id: dict[str, object] = {}

        probe = _ConfigurationWorkspaceProbe(_reflex_internal_init=True)

        probe.open_controller_profile_editor("int-2")

        self.assertEqual("configuration", probe.ui_workspace_mode)
        self.assertEqual("", probe.controller_profile_filter_text)
        self.assertEqual("all", probe.controller_profile_mapping_filter)
        self.assertEqual("int-2", probe.controller_profile_form_device_id)
        self.assertEqual("Broadway", probe.controller_profile_form_name)
        self.assertFalse(probe.controller_profile_form_polling_enabled)
        self.assertIn("paused for int-2", probe.managed_polling_notice)
        self.assertIn("Opened Controllers for int-2.", probe.controller_profile_notice)

    def test_configuration_state_initialize_controller_profiles_rehydrates_map_and_rows(self):
        class _ConfigurationLoadProbe(ConfigurationStateMixin, FleetStateMixin, rx.State):
            device_profiles_json: str = "[]"
            controller_profile_sort_key: str = "device_id"
            controller_profile_sort_desc: bool = False
            selected_device_id: str = ""
            fleet_status_by_id: dict[str, object] = {}
            auto_refresh_running: bool = True
            runtime_registry_refreshed: bool = False

            def refresh_runtime_registry_status(self):
                self.runtime_registry_refreshed = True

        probe = _ConfigurationLoadProbe(_reflex_internal_init=True)

        with patch("opensignal_its.states.configuration_state.STORE") as store, patch(
            "opensignal_its.states.configuration_state.PollingService.sync_runtime_registry",
            return_value=[],
        ) as sync_runtime_registry:
            store.get_app_setting.return_value = """[
                {
                    "device_id": "int-9",
                    "device_type": "siemens_m60",
                    "ip_address": "10.0.0.9",
                    "latitude": 40.7128,
                    "longitude": -74.0060
                }
            ]"""

            loop_spec = probe.initialize_controller_profiles()

        self.assertEqual(1, len(probe.controller_profile_rows))
        self.assertEqual(1, len(probe.fleet_map_markers))
        self.assertEqual(1, len(probe.fleet_status_cards))
        self.assertEqual("int-9", probe.selected_device_id)
        self.assertEqual("int-9", probe.controller_profile_form_device_id)
        self.assertTrue(probe.controller_profile_form_polling_enabled)
        self.assertFalse(probe.auto_refresh_running)
        self.assertTrue(probe.runtime_registry_refreshed)
        self.assertEqual("int-9", probe.controller_profile_rows[0]["device_id"])
        self.assertEqual("int-9", probe.fleet_map_markers[0]["device_id"])
        self.assertEqual("int-9", probe.fleet_status_cards[0]["device_id"])
        sync_runtime_registry.assert_called_once()
        self.assertEqual("int-9", sync_runtime_registry.call_args.args[0][0]["device_id"])
        self.assertIsNotNone(loop_spec)
        self.assertTrue(loop_spec.handler.is_background)
        self.assertEqual("auto_refresh_loop", loop_spec.handler.fn.__name__)

    def test_configuration_state_initialize_controller_profiles_prefers_last_loaded_controller_hint(self):
        class _ConfigurationLoadProbe(ConfigurationStateMixin, FleetStateMixin, rx.State):
            device_profiles_json: str = "[]"
            controller_profile_sort_key: str = "device_id"
            controller_profile_sort_desc: bool = False
            selected_device_id: str = ""
            controller_profile_original_device_id: str = "persist-1"
            controller_profile_form_device_id: str = "persist-1"
            fleet_status_by_id: dict[str, object] = {}

        probe = _ConfigurationLoadProbe(_reflex_internal_init=True)

        with patch("opensignal_its.states.configuration_state.STORE") as store:
            store.get_app_setting.return_value = """[
                {
                    "device_id": "000",
                    "device_type": "siemens_m60",
                    "ip_address": "166.156.88.223"
                },
                {
                    "device_id": "persist-1",
                    "device_type": "siemens_m60",
                    "ip_address": "10.0.0.11",
                    "polling_enabled": false
                }
            ]"""

            probe.initialize_controller_profiles()

        self.assertEqual("persist-1", probe.selected_device_id)
        self.assertEqual("persist-1", probe.controller_profile_form_device_id)
        self.assertFalse(probe.controller_profile_form_polling_enabled)

    def test_configuration_state_update_controller_profile_polling_enabled_updates_state_and_requests_refresh(self):
        class _ConfigurationPollingProbe(
            ConfigurationStateMixin,
            FleetStateMixin,
            PollingStateMixin,
            rx.State,
        ):
            device_profiles_json: str = """[
                {
                    "device_id": "int-4",
                    "device_type": "siemens_m60",
                    "ip_address": "10.0.0.4",
                    "polling_enabled": true
                }
            ]"""
            controller_profile_sort_key: str = "device_id"
            controller_profile_sort_desc: bool = False
            controller_profile_original_device_id: str = "int-4"
            selected_device_id: str = "int-4"
            fleet_status_by_id: dict[str, object] = {}

        probe = _ConfigurationPollingProbe(_reflex_internal_init=True)

        with patch("opensignal_its.states.configuration_state.STORE"):
            event_spec = probe.update_controller_profile_polling_enabled(False)

        self.assertFalse(probe.controller_profile_form_polling_enabled)
        self.assertIn('"polling_enabled": false', probe.device_profiles_json)
        self.assertIn("paused for int-4", probe.managed_polling_notice)
        self.assertIsNotNone(event_spec)
        self.assertEqual("refresh_fleet_status", event_spec.handler.fn.__name__)

    def test_configuration_state_save_controller_profile_preserves_existing_media_streams(self):
        class _ConfigurationSaveProbe(ConfigurationStateMixin, rx.State):
            device_profiles_json: str = """[
                {
                    "device_id": "int-7",
                    "name": "Broadway",
                    "location_name": "Broadway & Pine",
                    "device_type": "siemens_m60",
                    "ip_address": "10.0.0.7",
                    "port": 161,
                    "community": "public",
                    "snmp_version": "auto",
                    "timeout_seconds": 3.0,
                    "retries": 1,
                    "polling_enabled": true,
                    "media_streams": [
                        {
                            "stream_id": "cam-1",
                            "name": "Northbound",
                            "url": "rtsp://user:secret@camera.example.com/live",
                            "timeout_seconds": 4.5,
                            "enabled": true,
                            "metadata": {
                                "lane": "north"
                            }
                        }
                    ]
                }
            ]"""
            controller_profile_sort_key: str = "device_id"
            controller_profile_sort_desc: bool = False
            controller_profile_original_device_id: str = "int-7"
            controller_profile_form_device_id: str = "int-7"
            controller_profile_form_name: str = "Broadway Updated"
            controller_profile_form_location_name: str = "Broadway & Pine"
            controller_profile_form_device_type: str = "siemens_m60"
            controller_profile_form_ip_address: str = "10.0.0.7"
            controller_profile_form_port_text: str = "161"
            controller_profile_form_community: str = "public"
            controller_profile_form_snmp_version: str = "auto"
            controller_profile_form_timeout_text: str = "3"
            controller_profile_form_retries_text: str = "1"
            controller_profile_form_polling_enabled: bool = True
            selected_device_id: str = "int-7"
            fleet_status_by_id: dict[str, object] = {}
            runtime_registry_refreshed: bool = False

            def refresh_runtime_registry_status(self):
                self.runtime_registry_refreshed = True

        probe = _ConfigurationSaveProbe(_reflex_internal_init=True)

        with patch("opensignal_its.states.configuration_state.STORE"), patch(
            "opensignal_its.states.configuration_state.PollingService.sync_runtime_registry"
        ) as sync_runtime_registry:
            event_spec = probe.save_controller_profile()

        saved_profiles = json.loads(probe.device_profiles_json)

        self.assertEqual(1, len(saved_profiles))
        self.assertEqual("Broadway Updated", saved_profiles[0]["name"])
        self.assertEqual(1, len(saved_profiles[0]["media_streams"]))
        self.assertEqual("cam-1", saved_profiles[0]["media_streams"][0]["stream_id"])
        self.assertEqual(
            "rtsp://user:secret@camera.example.com/live",
            saved_profiles[0]["media_streams"][0]["url"],
        )
        self.assertIn("Saved controller profile int-7.", probe.controller_profile_notice)
        self.assertTrue(probe.runtime_registry_refreshed)
        sync_runtime_registry.assert_called_once()
        self.assertEqual("cam-1", sync_runtime_registry.call_args.args[0][0]["media_streams"][0]["stream_id"])
        self.assertIsNotNone(event_spec)

    def _make_monitor_media_probe(self, device_profiles_json: str):
        class _MonitorMediaProbe(MonitorStateMixin, FleetStateMixin, TimeStateMixin, rx.State):
            device_profiles_json: str = "[]"
            selected_device_id: str = ""
            fleet_status_by_id: dict[str, object] = {}
            fleet_map_markers: list[dict[str, object]] = []
            refresh_map_called: bool = False

            def _refresh_fleet_map_fields(self, profiles=None):
                self.refresh_map_called = True

        probe = _MonitorMediaProbe(_reflex_internal_init=True)
        probe.device_profiles_json = device_profiles_json
        return probe

    def test_monitor_state_loads_selected_controller_media_streams(self):
        probe = self._make_monitor_media_probe(
            """[
                {
                    "device_id": "int-1",
                    "device_type": "siemens_m60",
                    "ip_address": "10.0.0.1",
                    "media_streams": [
                        {
                            "stream_id": "cam-1",
                            "name": "Northbound",
                            "url": "rtsp://user:secret@camera.example.com/live/main",
                            "timeout_seconds": 4.5,
                            "enabled": true,
                            "metadata": {
                                "lane": "north",
                                "source": "rtsp://user:secret@camera.example.com/live/main"
                            }
                        }
                    ]
                }
            ]"""
        )

        probe.update_selected_device_id("int-1")

        self.assertTrue(probe.refresh_map_called)
        self.assertEqual(1, len(probe.selected_controller_media_streams))
        self.assertEqual("cam-1", probe.selected_controller_media_streams[0]["stream_id"])
        self.assertEqual(
            "rtsp://***@camera.example.com:554/live/main",
            probe.selected_controller_media_streams[0]["safe_url"],
        )
        self.assertEqual("1 media stream configured for int-1.", probe.selected_controller_media_notice)
        self.assertNotIn("secret", str(probe.selected_controller_media_streams))
        self.assertEqual("Not checked yet.", probe.selected_controller_media_rows[0]["status_text"])

    def test_monitor_state_loads_selected_controller_command_capabilities(self):
        probe = self._make_monitor_media_probe(
            """[
                {
                    "device_id": "int-1",
                    "device_type": "siemens_m60",
                    "ip_address": "10.0.0.1"
                }
            ]"""
        )

        class _CapabilityDevice:
            def get_capabilities(self):
                return {
                    "device_family": "traffic_signal_controller",
                    "protocol_family": "ntcip",
                    "command_capabilities": [
                        {
                            "command_id": "select_pattern",
                            "requires_confirmation": True,
                            "requires_value": True,
                            "value_type": "integer",
                            "allowed_values": [1, 2],
                            "options": [
                                {"value": 1, "label": "Plan A"},
                                {"value": 2, "label": "Plan B"},
                            ],
                        },
                        {
                            "command_id": "set_mode",
                            "requires_confirmation": True,
                            "requires_value": True,
                            "value_type": "string",
                            "allowed_values": ["free", "coordinated"],
                            "options": [
                                {"value": "free", "label": "Free Flow"},
                                {"value": "coordinated", "label": "Coord Plan"},
                            ],
                        },
                        {
                            "command_id": "manual_hold",
                            "requires_confirmation": True,
                            "requires_value": True,
                            "value_type": "boolean",
                            "allowed_values": [True, False],
                        },
                        {
                            "command_id": "advance_phase",
                            "requires_confirmation": True,
                            "requires_value": False,
                            "value_type": "none",
                        },
                    ],
                }

        with patch(
            "opensignal_its.states.monitor_state.Device.create",
            return_value=_CapabilityDevice(),
        ) as create_device:
            probe.update_selected_device_id("int-1")

        create_device.assert_called_once()
        self.assertEqual(4, len(probe.selected_controller_command_capabilities))
        self.assertEqual(
            "select_pattern",
            probe.selected_controller_command_capabilities[0]["command_id"],
        )
        self.assertEqual(
            [1, 2],
            probe.selected_controller_command_capabilities[0]["allowed_values"],
        )
        self.assertEqual(
            [
                {"value": 1, "label": "Plan A"},
                {"value": 2, "label": "Plan B"},
            ],
            probe.selected_controller_command_capabilities[0]["options"],
        )
        self.assertEqual(
            [
                {"action_id": "select_pattern_1", "label": "Plan A"},
                {"action_id": "select_pattern_2", "label": "Plan B"},
            ],
            probe.selected_controller_pattern_action_rows,
        )
        self.assertEqual(
            "string",
            probe.selected_controller_command_capabilities[1]["value_type"],
        )
        self.assertEqual(
            ["free", "coordinated"],
            probe.selected_controller_command_capabilities[1]["allowed_values"],
        )
        self.assertEqual(
            [
                {"action_id": "set_mode_free", "label": "Free Flow"},
                {"action_id": "set_mode_coordinated", "label": "Coord Plan"},
            ],
            probe.selected_controller_mode_action_rows,
        )
        self.assertEqual(
            "boolean",
            probe.selected_controller_command_capabilities[2]["value_type"],
        )
        self.assertEqual(
            [True, False],
            probe.selected_controller_command_capabilities[2]["allowed_values"],
        )
        self.assertEqual(
            "none",
            probe.selected_controller_command_capabilities[3]["value_type"],
        )
        self.assertTrue(probe.selected_controller_supports_select_pattern)
        self.assertTrue(probe.selected_controller_supports_set_mode)
        self.assertTrue(probe.selected_controller_supports_manual_hold)
        self.assertTrue(probe.selected_controller_supports_advance_phase)
        self.assertEqual(
            "4 command capabilities available for int-1.",
            probe.selected_controller_command_notice,
        )

    def test_monitor_state_preserves_dms_value_schema_in_capabilities(self):
        probe = self._make_monitor_media_probe(
            """[
                {
                    "device_id": "dms-1",
                    "device_type": "skyline_dms_emulator",
                    "ip_address": "10.0.1.20"
                }
            ]"""
        )

        value_schema = {
            "type": "object",
            "required": ["message"],
            "properties": {
                "message": {"type": "string", "min_length": 1, "max_length": 120},
                "activate_plan": {"type": "boolean"},
            },
        }

        class _CapabilityDevice:
            def get_capabilities(self):
                return {
                    "device_family": "dynamic_message_sign",
                    "protocol_family": "ntcip",
                    "command_capabilities": [
                        {
                            "command_id": "set_message",
                            "requires_confirmation": True,
                            "requires_value": True,
                            "value_type": "object",
                            "value_schema": value_schema,
                        }
                    ],
                }

        with patch(
            "opensignal_its.states.monitor_state.Device.create",
            return_value=_CapabilityDevice(),
        ):
            probe.update_selected_device_id("dms-1")

        self.assertEqual(1, len(probe.selected_controller_command_capabilities))
        self.assertEqual(
            "set_message",
            probe.selected_controller_command_capabilities[0]["command_id"],
        )
        self.assertEqual(
            value_schema,
            probe.selected_controller_command_capabilities[0]["value_schema"],
        )
        self.assertFalse(probe.selected_controller_supports_select_pattern)
        self.assertFalse(probe.selected_controller_supports_set_mode)
        self.assertEqual([], probe.selected_controller_pattern_action_rows)
        self.assertEqual([], probe.selected_controller_mode_action_rows)
        self.assertEqual(
            "1 command capability available for dms-1.",
            probe.selected_controller_command_notice,
        )

    def test_monitor_state_command_capability_unsupported_shape_returns_clear_empty_state(self):
        probe = self._make_monitor_media_probe(
            """[
                {
                    "device_id": "int-2",
                    "device_type": "siemens_m60",
                    "ip_address": "10.0.0.2"
                }
            ]"""
        )

        class _UnsupportedCapabilityDevice:
            def get_capabilities(self):
                return {
                    "device_family": "traffic_signal_controller",
                }

        with patch(
            "opensignal_its.states.monitor_state.Device.create",
            return_value=_UnsupportedCapabilityDevice(),
        ):
            probe.update_selected_device_id("int-2")

        self.assertEqual([], probe.selected_controller_command_capabilities)
        self.assertEqual([], probe.selected_controller_pattern_action_rows)
        self.assertEqual([], probe.selected_controller_mode_action_rows)
        self.assertFalse(probe.selected_controller_supports_select_pattern)
        self.assertFalse(probe.selected_controller_supports_set_mode)
        self.assertFalse(probe.selected_controller_supports_manual_hold)
        self.assertFalse(probe.selected_controller_supports_advance_phase)
        self.assertEqual(
            "Command capabilities are unavailable for the selected controller.",
            probe.selected_controller_command_notice,
        )

    def test_monitor_state_quick_action_rows_ignore_unsupported_capability_options(self):
        probe = self._make_monitor_media_probe(
            """[
                {
                    "device_id": "int-3",
                    "device_type": "siemens_m60",
                    "ip_address": "10.0.0.3"
                }
            ]"""
        )

        class _CapabilityDevice:
            def get_capabilities(self):
                return {
                    "device_family": "traffic_signal_controller",
                    "protocol_family": "ntcip",
                    "command_capabilities": [
                        {
                            "command_id": "select_pattern",
                            "requires_confirmation": True,
                            "requires_value": True,
                            "value_type": "integer",
                            "options": [
                                {"value": 2, "label": "Plan B"},
                                {"value": 9, "label": "Plan 9"},
                            ],
                        },
                        {
                            "command_id": "set_mode",
                            "requires_confirmation": True,
                            "requires_value": True,
                            "value_type": "string",
                            "allowed_values": ["free", "flash"],
                        },
                    ],
                }

        with patch(
            "opensignal_its.states.monitor_state.Device.create",
            return_value=_CapabilityDevice(),
        ):
            probe.update_selected_device_id("int-3")

        self.assertEqual(
            [{"action_id": "select_pattern_2", "label": "Plan B"}],
            probe.selected_controller_pattern_action_rows,
        )
        self.assertEqual(
            [{"action_id": "set_mode_free", "label": "Free"}],
            probe.selected_controller_mode_action_rows,
        )

    def test_monitor_state_selected_controller_media_empty_state_without_media_streams(self):
        probe = self._make_monitor_media_probe(
            """[
                {
                    "device_id": "int-2",
                    "device_type": "siemens_m60",
                    "ip_address": "10.0.0.2"
                }
            ]"""
        )

        probe.update_selected_device_id("int-2")

        self.assertEqual([], probe.selected_controller_media_streams)
        self.assertEqual([], probe.selected_controller_media_statuses)
        self.assertEqual([], probe.selected_controller_media_rows)
        self.assertEqual(
            "No media streams configured for the selected controller.",
            probe.selected_controller_media_notice,
        )

    def test_monitor_state_refresh_selected_controller_media_stream_health_uses_describe_results(self):
        probe = self._make_monitor_media_probe(
            """[
                {
                    "device_id": "int-1",
                    "device_type": "siemens_m60",
                    "ip_address": "10.0.0.1",
                    "media_streams": [
                        {
                            "stream_id": "cam-1",
                            "name": "Northbound",
                            "url": "rtsp://user:secret@camera.example.com/live/main",
                            "timeout_seconds": 4.5,
                            "enabled": true,
                            "metadata": {
                                "lane": "north"
                            }
                        }
                    ]
                }
            ]"""
        )
        probe.update_selected_device_id("int-1")

        async def _fake_describe_stream_protocol(stream_config):
            return MediaStreamStatus(
                stream_id=stream_config.stream_id,
                name=stream_config.name,
                enabled=stream_config.enabled,
                is_online=True,
                status_text="RTSP DESCRIBE succeeded",
                safe_url="rtsp://***@camera.example.com:554/live/main",
                latency_ms=12.5,
                errors=[],
                raw_data={},
                extra={"lane": "north", "probe": "describe", "status_code": 200},
            )

        with patch(
            "opensignal_its.states.monitor_state.MediaService.describe_stream_protocol",
            side_effect=_fake_describe_stream_protocol,
        ) as describe_stream_protocol:
            asyncio.run(probe.refresh_selected_controller_media_stream_health())

        describe_stream_protocol.assert_called_once()
        self.assertFalse(probe.selected_controller_media_loading)
        self.assertEqual(1, len(probe.selected_controller_media_statuses))
        self.assertEqual("cam-1", probe.selected_controller_media_statuses[0]["stream_id"])
        self.assertEqual("RTSP DESCRIBE succeeded", probe.selected_controller_media_rows[0]["status_text"])
        self.assertEqual("Online", probe.selected_controller_media_rows[0]["status_label"])
        self.assertEqual("12.5 ms", probe.selected_controller_media_rows[0]["latency_text"])
        self.assertIn("Checked 1 media stream for int-1.", probe.selected_controller_media_notice)
        self.assertNotIn("secret", str(probe.selected_controller_media_statuses))

    def test_monitor_state_media_config_errors_do_not_leak_credentials(self):
        probe = self._make_monitor_media_probe(
            """[
                {
                    "device_id": "int-9",
                    "device_type": "siemens_m60",
                    "ip_address": "10.0.0.9",
                    "media_streams": [
                        {
                            "stream_id": "cam-9",
                            "url": "http://user:secret@camera.example.com/live"
                        }
                    ]
                }
            ]"""
        )

        probe.update_selected_device_id("int-9")

        self.assertEqual([], probe.selected_controller_media_streams)
        self.assertEqual([], probe.selected_controller_media_statuses)
        self.assertEqual([], probe.selected_controller_media_rows)
        self.assertEqual(
            "Media stream configuration is unavailable for the selected controller.",
            probe.selected_controller_media_notice,
        )
        self.assertNotIn("secret", probe.selected_controller_media_notice)
        self.assertNotIn("user", probe.selected_controller_media_notice)

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

    def test_fleet_state_refresh_fleet_map_fields_builds_friendly_unmapped_rows(self):
        class _FleetProbe(FleetStateMixin, rx.State):
            device_profiles_json: str = """[
                {
                    "device_id": "int-1",
                    "name": "Broadway",
                    "location_name": "Broadway & Pine",
                    "device_type": "siemens_m60",
                    "ip_address": "10.0.0.1"
                },
                {
                    "device_id": "int-2",
                    "device_type": "siemens_m60",
                    "ip_address": "10.0.0.2",
                    "latitude": 40.7128,
                    "longitude": -74.0060
                }
            ]"""
            selected_device_id: str = ""
            fleet_status_by_id: dict[str, object] = {}

        probe = _FleetProbe(_reflex_internal_init=True)

        probe._refresh_fleet_map_fields()

        self.assertEqual(["int-1"], probe.fleet_unmapped_device_ids)
        self.assertEqual(["int-1"], [row["device_id"] for row in probe.fleet_unmapped_profile_rows])
        self.assertEqual("Broadway & Pine", probe.fleet_unmapped_profile_rows[0]["title"])
        self.assertEqual("Coordinates not set", probe.fleet_unmapped_profile_rows[0]["coordinate_text"])

    def test_fleet_state_refresh_fleet_status_applies_selected_payload_through_shared_helper(self):
        probe = self._make_selected_status_probe()
        payload = {
            "is_online": True,
            "status_text": "ok",
            "timestamp": "2026-05-27T00:00:00+00:00",
            "raw_data": {},
            "extra": {},
            "errors": [],
        }
        adapted = {
            "selected_device_id": "int-1",
            "fleet_status_by_id": {},
            "fleet_device_rows": ["int-1 [siemens_m60] ONLINE - ok"],
            "selected_payload": payload,
            "selected_mp_model": 1,
            "selected_device_type": "siemens_m60",
        }

        with patch(
            "opensignal_its.states.fleet_state._fleet_view_to_state_fields",
            return_value=adapted,
        ), patch(
            "opensignal_its.states.fleet_state.PollingService.sync_runtime_registry",
        ) as sync_runtime_registry, patch.object(
            type(probe),
            "_apply_selected_status_result",
            wraps=probe._apply_selected_status_result,
        ) as apply_selected_status_result:
            asyncio.run(probe.refresh_fleet_status())

        apply_selected_status_result.assert_called_once_with("int-1", "siemens_m60", payload, 1)
        self.assertEqual("int-1", probe.selected_device_id)
        self.assertEqual(("int-1", "siemens_m60", payload), probe.cached_status)
        self.assertTrue(probe.is_online)
        self.assertEqual("ok", probe.status_text)
        self.assertEqual("2026-05-27T00:00:00+00:00", probe.last_updated)
        self.assertTrue(probe.refresh_cards_called)
        self.assertTrue(probe.refresh_map_called)
        self.assertTrue(probe.sync_rows_called)
        self.assertTrue(probe.aggregate_refreshed)
        self.assertTrue(probe.runtime_registry_refreshed)
        self.assertIn("int-1", probe.fleet_status_by_id)
        self.assertEqual("ok", probe.fleet_status_by_id["int-1"]["status_text"])
        sync_runtime_registry.assert_called_once()

    def test_fleet_state_refresh_fleet_status_uses_selected_status_fallback_without_selected_payload(self):
        probe = self._make_selected_status_probe()
        fallback_timestamp = "2026-05-27T00:00:01+00:00"
        adapted = {
            "selected_device_id": "int-1",
            "fleet_status_by_id": {
                "int-1": {
                    "device_type": "siemens_m60",
                    "is_online": True,
                    "status_text": "Cached OK",
                    "timestamp": fallback_timestamp,
                }
            },
            "fleet_device_rows": ["int-1 [siemens_m60] ONLINE - Cached OK"],
            "selected_payload": None,
            "selected_mp_model": 1,
            "selected_device_type": "siemens_m60",
        }

        with patch(
            "opensignal_its.states.fleet_state._fleet_view_to_state_fields",
            return_value=adapted,
        ), patch(
            "opensignal_its.states.fleet_state.PollingService.sync_runtime_registry",
        ) as sync_runtime_registry:
            asyncio.run(probe.refresh_fleet_status())

        self.assertIsNone(probe.cached_status)
        self.assertTrue(probe.is_online)
        self.assertEqual("Cached OK", probe.status_text)
        self.assertEqual(fallback_timestamp, probe.last_updated)
        self.assertTrue(probe.refresh_cards_called)
        self.assertTrue(probe.refresh_map_called)
        self.assertTrue(probe.sync_rows_called)
        self.assertTrue(probe.aggregate_refreshed)
        self.assertTrue(probe.runtime_registry_refreshed)
        sync_runtime_registry.assert_called_once()

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

    def test_monitor_state_connect_uses_connection_status_path(self):
        probe = self._make_selected_status_probe()
        payload = {
            "is_online": True,
            "status_text": "Connected via SNMP v1",
            "timestamp": "2026-05-26T00:00:00+00:00",
            "raw_data": {},
            "extra": {},
            "errors": [],
        }

        async def _fake_collect_connection_status(device_type, config, device_id=""):
            return payload, 0

        with patch(
            "opensignal_its.states.monitor_state.PollingService.collect_connection_status",
            side_effect=_fake_collect_connection_status,
        ) as collect_connection_status, patch(
            "opensignal_its.states.monitor_state.PollingService.collect_snapshot"
        ) as collect_snapshot, patch.object(
            type(probe),
            "_apply_selected_status_result",
            wraps=probe._apply_selected_status_result,
        ) as apply_selected_status_result:
            asyncio.run(probe.connect_m60())

        collect_connection_status.assert_called_once()
        collect_snapshot.assert_not_called()
        apply_selected_status_result.assert_called_once_with("int-1", "siemens_m60", payload, 0)
        self.assertTrue(probe.is_online)
        self.assertEqual("Connected via SNMP v1", probe.status_text)
        self.assertEqual(("int-1", "siemens_m60", payload), probe.cached_status)

    def _make_selected_status_probe(self):
        class _SelectedStatusProbe(MonitorStateMixin, FleetStateMixin, TimeStateMixin, rx.State):
            device_profiles_json: str = """[
                {
                    "device_id": "int-1",
                    "device_type": "siemens_m60",
                    "ip_address": "10.0.0.1",
                    "polling_enabled": false
                }
            ]"""
            selected_device_id: str = "int-1"
            auto_refresh_enabled: bool = False
            auto_reconnect_enabled: bool = False
            last_updated: str = ""
            is_loading: bool = False
            error: str = ""
            m60_status: dict = {}
            m60_status_json: str = ""
            status_text: str = ""
            active_snmp_version: str = "unknown"
            is_online: bool = False
            fleet_status_by_id: dict[str, object] = {}
            fleet_status_cards: list[dict[str, str]] = []
            fleet_device_rows: list[str] = []
            fleet_status_mapping_filter: str = "all"
            fleet_status_card_notice: str = ""
            fleet_map_markers: list[dict[str, object]] = []
            fleet_unmapped_device_ids: list[str] = []
            fleet_unmapped_profile_rows: list[dict[str, str]] = []
            fleet_map_data: list[dict[str, object]] = []
            fleet_map_layout: dict[str, object] = {}
            fleet_map_figure: dict[str, object] = {}
            fleet_map_src_doc: str = ""
            fleet_map_notice: str = ""
            fleet_online_count: int = 0
            fleet_offline_count: int = 0
            fleet_total_count: int = 0
            cached_status: tuple[str, str, dict] | None = None
            refresh_cards_called: bool = False
            refresh_map_called: bool = False
            sync_rows_called: bool = False
            aggregate_refreshed: bool = False
            runtime_registry_refreshed: bool = False

            def _selected_device_target(self):
                return (
                    "siemens_m60",
                    "int-1",
                    type(
                        "_Config",
                        (),
                        {
                            "ip_address": "10.0.0.1",
                            "port": 161,
                            "community": "public",
                            "snmp_version": "v1",
                            "timeout_seconds": 3.0,
                            "retries": 1,
                            "name": "Fake",
                        },
                    )(),
                )

            def _refresh_fleet_card_fields(self, profiles=None):
                self.refresh_cards_called = True

            def _refresh_fleet_map_fields(self, profiles=None):
                self.refresh_map_called = True

            def _sync_controller_profile_rows(self, notice: str = ""):
                self.sync_rows_called = True

            def _refresh_fleet_aggregate_fields(self):
                self.aggregate_refreshed = True

            def refresh_runtime_registry_status(self):
                self.runtime_registry_refreshed = True

            def _cache_device_status(self, device_id: str, device_type: str, payload: dict):
                self.cached_status = (device_id, device_type, payload)
                return super()._cache_device_status(device_id, device_type, payload)

        return _SelectedStatusProbe(_reflex_internal_init=True)

    def _make_monitor_selection_probe(self):
        class _MonitorSelectionProbe(MonitorStateMixin, rx.State):
            selected_device_id: str = ""
            monitor_view: str = "dashboard"
            fleet_map_markers: list[dict[str, object]] = []
            loaded_device_id: str = ""
            close_called: bool = False
            refresh_map_called: bool = False
            refresh_called: bool = False

            def load_controller_profile_from_row(self, device_id: str):
                self.loaded_device_id = device_id

            def close_controller_profile_creation_dialog(self):
                self.close_called = True

            def _refresh_fleet_map_fields(self):
                self.refresh_map_called = True

            async def refresh_fleet_status(self):
                self.refresh_called = True

        return _MonitorSelectionProbe(_reflex_internal_init=True)

    def _make_command_status_probe(self):
        class _CommandStatusProbe(CommandStateMixin, MonitorStateMixin, FleetStateMixin, TimeStateMixin, rx.State):
            selected_device_id: str = "int-1"
            safe_command_probe: bool = False
            write_unlock_until: str = ""
            write_mode_active: bool = False
            safety_notice: str = ""
            ip_address: str = "166.156.88.223"
            is_loading: bool = False
            error: str = ""
            m60_status: dict = {}
            m60_status_json: str = ""
            status_text: str = ""
            active_snmp_version: str = "unknown"
            is_online: bool = False
            last_updated: str = ""
            fleet_status_by_id: dict[str, object] = {}
            fleet_status_cards: list[dict[str, str]] = []
            fleet_device_rows: list[str] = []
            fleet_status_mapping_filter: str = "all"
            fleet_status_card_notice: str = ""
            fleet_map_markers: list[dict[str, object]] = []
            fleet_unmapped_device_ids: list[str] = []
            fleet_unmapped_profile_rows: list[dict[str, str]] = []
            fleet_map_data: list[dict[str, object]] = []
            fleet_map_layout: dict[str, object] = {}
            fleet_map_figure: dict[str, object] = {}
            fleet_map_src_doc: str = ""
            fleet_map_notice: str = ""
            fleet_online_count: int = 0
            fleet_offline_count: int = 0
            fleet_total_count: int = 0
            cached_status: tuple[str, str, dict] | None = None
            status_log_calls: list[tuple[str, str, dict]] = []

            def _selected_device_target(self):
                return (
                    "siemens_m60",
                    "int-1",
                    type(
                        "_Config",
                        (),
                        {
                            "ip_address": "10.0.0.1",
                            "port": 161,
                            "community": "public",
                            "snmp_version": "v1",
                            "timeout_seconds": 3.0,
                            "retries": 1,
                            "name": "Fake",
                        },
                    )(),
                )

            def _is_role_authorized(self, allowed_roles):
                return True

            def _requires_confirmation(self, cmd_type):
                return False

            def _actor_name(self):
                return "operator"

            def _safe_log_status_snapshot(self, payload: dict, correlation_id: str = "", source: str = "poll"):
                self.status_log_calls.append((correlation_id, source, dict(payload)))

            def _sync_controller_profile_rows(self, notice: str = ""):
                return None

            def _cache_device_status(self, device_id: str, device_type: str, payload: dict):
                self.cached_status = (device_id, device_type, payload)
                return super()._cache_device_status(device_id, device_type, payload)

        return _CommandStatusProbe(_reflex_internal_init=True)

    def test_monitor_state_add_and_poll_m60_routes_successful_result_through_shared_helper(self):
        probe = self._make_selected_status_probe()
        payload = {
            "is_online": True,
            "status_text": "polled",
            "timestamp": "2026-05-27T00:00:00+00:00",
            "raw_data": {},
            "extra": {},
            "errors": [],
        }

        async def _fake_collect_snapshot(device_type, config, device_id=""):
            return payload, 1

        with patch(
            "opensignal_its.states.monitor_state.PollingService.collect_snapshot",
            side_effect=_fake_collect_snapshot,
        ) as collect_snapshot, patch.object(
            type(probe),
            "_apply_selected_status_result",
            wraps=probe._apply_selected_status_result,
        ) as apply_selected_status_result:
            asyncio.run(probe.add_and_poll_m60())

        collect_snapshot.assert_called_once()
        apply_selected_status_result.assert_called_once_with("int-1", "siemens_m60", payload, 1)
        self.assertEqual(("int-1", "siemens_m60", payload), probe.cached_status)
        self.assertTrue(probe.is_online)
        self.assertEqual("polled", probe.status_text)
        self.assertEqual("v2c", probe.active_snmp_version)
        self.assertEqual("", probe.error)
        self.assertFalse(probe.is_loading)

    def test_monitor_state_refreshes_after_row_selection(self):
        probe = self._make_monitor_selection_probe()

        asyncio.run(probe.select_controller_from_row("int-2 | Broadway"))

        self.assertEqual("int-2", probe.loaded_device_id)
        self.assertTrue(probe.close_called)
        self.assertTrue(probe.refresh_map_called)
        self.assertTrue(probe.refresh_called)
        self.assertEqual("int-2", probe.selected_device_id)
        self.assertEqual("intersection", probe.monitor_view)

    def test_monitor_state_refreshes_after_map_point_selection(self):
        probe = self._make_monitor_selection_probe()
        probe.fleet_map_markers = [{"device_id": "int-7"}]

        asyncio.run(
            probe.select_controller_from_map_points(
                [
                    {
                        "pointNumber": 0,
                    }
                ]
            )
        )

        self.assertEqual("int-7", probe.loaded_device_id)
        self.assertTrue(probe.close_called)
        self.assertTrue(probe.refresh_map_called)
        self.assertTrue(probe.refresh_called)
        self.assertEqual("int-7", probe.selected_device_id)
        self.assertEqual("intersection", probe.monitor_view)

    def test_monitor_state_selects_controller_creation_point_from_map_click(self):
        class _MonitorCreateProbe(ConfigurationStateMixin, MonitorStateMixin, rx.State):
            controller_profile_creation_dialog_open: bool = False
            controller_profile_map_point_latitude_text: str = ""
            controller_profile_map_point_longitude_text: str = ""
            controller_profile_form_latitude_text: str = ""
            controller_profile_form_longitude_text: str = ""

        probe = _MonitorCreateProbe(_reflex_internal_init=True)

        asyncio.run(probe.sync_map_selection_from_storage(
            "opensignal-map-create-controller",
            "",
            '{"latitude": 40.7128, "longitude": -74.0060, "source": "map-click"}',
            "http://localhost:3000/",
        ))

        self.assertFalse(probe.controller_profile_creation_dialog_open)
        self.assertEqual("40.7128", probe.controller_profile_map_point_latitude_text)
        self.assertEqual("-74.006", probe.controller_profile_map_point_longitude_text)
        self.assertEqual("Selected a map point. Click Add to open the controller dialog.", probe.controller_profile_notice)

    def test_monitor_state_refreshes_after_map_selection(self):
        probe = self._make_monitor_selection_probe()

        asyncio.run(
            probe.sync_map_selection_from_storage(
                "opensignal-map-selection",
                "",
                "int-7::12345",
                "http://localhost:3000/",
            )
        )

        self.assertEqual("int-7", probe.loaded_device_id)
        self.assertTrue(probe.close_called)
        self.assertTrue(probe.refresh_map_called)
        self.assertTrue(probe.refresh_called)
        self.assertEqual("int-7", probe.selected_device_id)
        self.assertEqual("intersection", probe.monitor_view)

    def test_monitor_state_ignores_blank_row_and_invalid_map_point_index(self):
        probe = self._make_monitor_selection_probe()
        probe.fleet_map_markers = [{"device_id": "int-7"}]

        asyncio.run(probe.select_controller_from_row("   "))
        asyncio.run(probe.select_controller_from_map_points([{"pointNumber": 1}]))

        self.assertEqual("", probe.selected_device_id)
        self.assertEqual("dashboard", probe.monitor_view)
        self.assertEqual("", probe.loaded_device_id)
        self.assertFalse(probe.close_called)
        self.assertFalse(probe.refresh_map_called)
        self.assertFalse(probe.refresh_called)

    def test_monitor_state_connect_and_start_polling_starts_managed_polling(self):
        class _MonitorConnectProbe(MonitorStateMixin, FleetStateMixin, PollingStateMixin, rx.State):
            is_online: bool = False
            managed_polling_notice: str = ""
            managed_polling_interval_text: str = "7"
            runtime_registry_summary: str = ""
            runtime_registry_rows: list[str] = []
            auto_refresh_enabled: bool = False
            auto_reconnect_enabled: bool = False
            health_refreshed: bool = False
            registry_refreshed: bool = False
            connect_called: bool = False
            start_called: bool = False
            auto_refresh_loop = TrafficState.auto_refresh_loop

            def refresh_runtime_health(self):
                self.health_refreshed = True

            def refresh_runtime_registry_status(self):
                self.registry_refreshed = True

            async def connect_m60(self):
                self.connect_called = True
                self.is_online = True

            async def start_selected_managed_polling(self):
                self.start_called = True
                self.managed_polling_notice = "Managed polling started. Refreshing every 7s."
                return True

        probe = _MonitorConnectProbe(_reflex_internal_init=True)

        loop_spec = asyncio.run(probe.connect_and_start_polling())

        self.assertTrue(probe.connect_called)
        self.assertTrue(probe.start_called)
        self.assertTrue(probe.health_refreshed)
        self.assertTrue(probe.registry_refreshed)
        self.assertTrue(probe.auto_refresh_enabled)
        self.assertTrue(probe.auto_reconnect_enabled)
        self.assertIsNotNone(loop_spec)
        self.assertTrue(loop_spec.handler.is_background)
        self.assertEqual("auto_refresh_loop", loop_spec.handler.fn.__name__)
        self.assertIn("Refreshing every 7s.", probe.managed_polling_notice)

    def test_monitor_state_connect_and_start_polling_still_attempts_restart_when_probe_is_offline(self):
        class _MonitorConnectProbe(MonitorStateMixin, FleetStateMixin, PollingStateMixin, rx.State):
            is_online: bool = False
            managed_polling_notice: str = ""
            managed_polling_interval_text: str = "7"
            runtime_registry_summary: str = ""
            runtime_registry_rows: list[str] = []
            auto_refresh_enabled: bool = False
            auto_reconnect_enabled: bool = False
            connect_called: bool = False
            start_called: bool = False

            def refresh_runtime_health(self):
                pass

            def refresh_runtime_registry_status(self):
                pass

            async def connect_m60(self):
                self.connect_called = True
                self.is_online = False

            async def start_selected_managed_polling(self):
                self.start_called = True
                self.managed_polling_notice = "Managed polling start attempted."

        probe = _MonitorConnectProbe(_reflex_internal_init=True)

        asyncio.run(probe.connect_and_start_polling())

        self.assertTrue(probe.connect_called)
        self.assertTrue(probe.start_called)
        self.assertTrue(probe.auto_refresh_enabled)
        self.assertTrue(probe.auto_reconnect_enabled)
        self.assertIn("Managed polling start attempted.", probe.managed_polling_notice)

    def test_polling_state_stop_selected_managed_polling_clears_auto_refresh_flags(self):
        class _PollingProbe(FleetStateMixin, PollingStateMixin, rx.State):
            selected_device_id: str = "int-1"
            auto_refresh_enabled: bool = True
            auto_reconnect_enabled: bool = True
            managed_polling_notice: str = ""
            error: str = ""
            runtime_registry_refreshed: bool = False

            def _selected_device_target(self):
                return (
                    "siemens_m60",
                    "int-1",
                    type(
                        "_Config",
                        (),
                        {
                            "ip_address": "10.0.0.1",
                            "port": 161,
                            "community": "public",
                            "snmp_version": "v1",
                            "timeout_seconds": 3.0,
                            "retries": 1,
                            "name": "Fake",
                        },
                    )(),
                )

            def refresh_runtime_registry_status(self):
                self.runtime_registry_refreshed = True

        probe = _PollingProbe(_reflex_internal_init=True)

        with patch(
            "opensignal_its.states.polling_state.PollingService.stop_managed_polling",
            return_value=(True, "Managed polling stopped for siemens_m60::int-1."),
        ):
            probe.stop_selected_managed_polling()

        self.assertFalse(probe.auto_refresh_enabled)
        self.assertFalse(probe.auto_reconnect_enabled)
        self.assertTrue(probe.runtime_registry_refreshed)
        self.assertIn("stopped", probe.managed_polling_notice)

    def test_polling_state_start_selected_managed_polling_announces_interval(self):
        class _PollingProbe(PollingStateMixin, rx.State):
            selected_device_id: str = "int-1"
            managed_polling_interval_text: str = "7"
            managed_polling_notice: str = ""
            error: str = ""
            runtime_registry_refreshed: bool = False

            def _selected_device_target(self):
                return (
                    "siemens_m60",
                    "int-1",
                    type("_Config", (), {"ip_address": "10.0.0.1", "port": 161, "community": "public", "snmp_version": "v1", "timeout_seconds": 3.0, "retries": 1, "name": "Fake"})(),
                )

            def refresh_runtime_registry_status(self):
                self.runtime_registry_refreshed = True

        async def _fake_start_managed_polling(device_type, config, device_id="", interval_seconds=5):
            return True, f"Managed polling started for {device_id}."

        probe = _PollingProbe(_reflex_internal_init=True)

        with patch(
            "opensignal_its.states.polling_state.PollingService.start_managed_polling",
            side_effect=_fake_start_managed_polling,
        ):
            asyncio.run(probe.start_selected_managed_polling())

        self.assertTrue(probe.runtime_registry_refreshed)
        self.assertIn("Refreshing every 7s.", probe.managed_polling_notice)

    def test_configuration_state_open_controller_creation_dialog_uses_selected_map_point(self):
        class _ConfigurationCreateProbe(ConfigurationStateMixin, rx.State):
            controller_profile_map_point_latitude_text: str = "40.7128"
            controller_profile_map_point_longitude_text: str = "-74.006"

        probe = _ConfigurationCreateProbe(_reflex_internal_init=True)

        probe.open_controller_profile_creation_dialog()

        self.assertTrue(probe.controller_profile_creation_dialog_open)
        self.assertEqual("40.7128", probe.controller_profile_form_latitude_text)
        self.assertEqual("-74.006", probe.controller_profile_form_longitude_text)
        self.assertIn("selected map point", probe.controller_profile_notice.lower())

    def test_command_state_select_pattern_wrapper_delegates_to_send_command(self):
        class _CommandProbe(CommandStateMixin, rx.State):
            calls: list[tuple[object, object, object]] = []

            async def send_command(self, cmd_type, value, force_confirmed=False):
                self.calls.append((cmd_type, value, force_confirmed))

        probe = _CommandProbe(_reflex_internal_init=True)
        probe.calls = []

        asyncio.run(probe.select_pattern_1())

        self.assertEqual([("select_pattern", 1, False)], probe.calls)

    def test_command_state_wrappers_delegate_existing_command_ids(self):
        class _CommandProbe(CommandStateMixin, rx.State):
            calls: list[tuple[object, object, object]] = []

            async def send_command(self, cmd_type, value, force_confirmed=False):
                self.calls.append((cmd_type, value, force_confirmed))

        probe = _CommandProbe(_reflex_internal_init=True)
        probe.calls = []

        asyncio.run(probe.select_pattern_2())
        asyncio.run(probe.set_mode_free())
        asyncio.run(probe.set_mode_coordinated())
        asyncio.run(probe.manual_hold())
        asyncio.run(probe.advance_phase())

        self.assertEqual(
            [
                ("select_pattern", 2, False),
                ("set_mode", "free", False),
                ("set_mode", "coordinated", False),
                ("manual_hold", True, False),
                ("advance_phase", True, False),
            ],
            probe.calls,
        )

    def test_safety_state_requires_confirmation_routes_through_command_catalog(self):
        class _SafetyProbe(SafetyStateMixin, rx.State):
            safe_command_probe: bool = False

        probe = _SafetyProbe(_reflex_internal_init=True)

        with patch(
            "opensignal_its.states.safety_state.command_requires_confirmation",
            return_value=True,
        ) as command_requires_confirmation:
            self.assertTrue(probe._requires_confirmation("manual_hold"))

        command_requires_confirmation.assert_called_once_with("manual_hold")

        probe.safe_command_probe = True
        with patch(
            "opensignal_its.states.safety_state.command_requires_confirmation",
            return_value=True,
        ) as command_requires_confirmation:
            self.assertFalse(probe._requires_confirmation("manual_hold"))

        command_requires_confirmation.assert_not_called()

    def test_command_state_confirmation_required_sets_lifecycle_state(self):
        class _CommandConfirmationProbe(CommandStateMixin, SafetyStateMixin, TimeStateMixin, rx.State):
            ip_address: str = "10.0.0.1"
            error: str = ""
            is_loading: bool = False

            def _is_role_authorized(self, allowed_roles):
                return True

            def _actor_name(self):
                return "operator"

            def _requires_confirmation(self, cmd_type):
                return True

        probe = _CommandConfirmationProbe(_reflex_internal_init=True)
        probe.safe_command_probe = False

        with patch("opensignal_its.states.command_state.uuid4", return_value=type("_Uuid", (), {"hex": "corr-await"})()), patch(
            "opensignal_its.states.command_state.STORE.log_command",
        ):
            asyncio.run(probe.send_command("set_mode", "free"))

        self.assertEqual("awaiting_confirmation", probe.selected_controller_command_lifecycle["stage"])
        self.assertEqual("set_mode", probe.selected_controller_command_lifecycle["command_id"])
        self.assertEqual("corr-await", probe.selected_controller_command_lifecycle["correlation_id"])
        self.assertFalse(probe.selected_controller_command_lifecycle["is_terminal"])
        self.assertEqual("corr-await", probe.pending_command_correlation_id)
        self.assertIn("Awaiting Confirmation:", probe.selected_controller_command_lifecycle_notice)
        self.assertIn("Confirmation required for set_mode.", probe.selected_controller_command_lifecycle_notice)

    def test_safety_state_confirm_pending_command_expired_sets_lifecycle_state(self):
        class _CommandConfirmationProbe(CommandStateMixin, SafetyStateMixin, TimeStateMixin, rx.State):
            error: str = ""
            is_loading: bool = False

        probe = _CommandConfirmationProbe(_reflex_internal_init=True)
        probe.pending_command_type = "set_mode"
        probe.pending_command_value_json = json.dumps("free")
        probe.pending_command_correlation_id = "corr-expired"
        probe.pending_confirmation_token = "123456"
        probe.pending_confirmation_expires = "2000-01-01T00:00:00+00:00"

        asyncio.run(probe.confirm_pending_command())

        self.assertEqual("Confirmation token expired.", probe.error)
        self.assertEqual("confirmation_expired", probe.selected_controller_command_lifecycle["stage"])
        self.assertEqual("set_mode", probe.selected_controller_command_lifecycle["command_id"])
        self.assertEqual("corr-expired", probe.selected_controller_command_lifecycle["correlation_id"])
        self.assertTrue(probe.selected_controller_command_lifecycle["is_terminal"])
        self.assertEqual("", probe.pending_command_correlation_id)
        self.assertIn("Confirmation Expired:", probe.selected_controller_command_lifecycle_notice)

    def test_safety_state_confirm_pending_command_mismatch_sets_lifecycle_state(self):
        class _CommandConfirmationProbe(CommandStateMixin, SafetyStateMixin, TimeStateMixin, rx.State):
            error: str = ""
            is_loading: bool = False

        probe = _CommandConfirmationProbe(_reflex_internal_init=True)
        probe.pending_command_type = "set_mode"
        probe.pending_command_value_json = json.dumps("free")
        probe.pending_command_correlation_id = "corr-reject"
        probe.pending_confirmation_token = "123456"
        probe.pending_confirmation_expires = probe._utc_future_iso(60)
        probe.confirmation_input = "000000"

        asyncio.run(probe.confirm_pending_command())

        self.assertEqual("Confirmation token mismatch.", probe.error)
        self.assertEqual("confirmation_rejected", probe.selected_controller_command_lifecycle["stage"])
        self.assertEqual("set_mode", probe.selected_controller_command_lifecycle["command_id"])
        self.assertEqual("corr-reject", probe.selected_controller_command_lifecycle["correlation_id"])
        self.assertFalse(probe.selected_controller_command_lifecycle["is_terminal"])
        self.assertEqual("123456", probe.pending_confirmation_token)
        self.assertIn("Confirmation Rejected:", probe.selected_controller_command_lifecycle_notice)

    def test_command_state_send_command_routes_success_through_shared_helper(self):
        probe = self._make_command_status_probe()
        probe.status_log_calls = []
        probe.write_unlock_until = probe._utc_future_iso(60)
        payload = {
            "is_online": True,
            "timestamp": "2026-05-27T00:00:03+00:00",
            "raw_data": {},
            "extra": {},
            "errors": [],
        }

        async def _fake_execute_command_result(device_type, config, cmd_type, value, safe_command_probe, device_id=""):
            return CommandExecutionResult(
                success=True,
                payload=payload,
                mp_model=1,
                error="",
                lifecycle_stage="applied",
                lifecycle_notice="Command applied.",
                acknowledged=True,
            )

        with patch("opensignal_its.states.command_state.uuid4", return_value=type("_Uuid", (), {"hex": "corr-123"})()), patch(
            "opensignal_its.states.command_state.CommandService.execute_command_result",
            side_effect=_fake_execute_command_result,
        ) as execute_command_result, patch(
            "opensignal_its.states.command_state.STORE.log_command",
        ) as log_command, patch.object(
            type(probe),
            "_apply_selected_status_result",
            wraps=probe._apply_selected_status_result,
        ) as apply_selected_status_result:
            asyncio.run(probe.send_command("set_mode", "free"))

        execute_command_result.assert_awaited_once()
        apply_selected_status_result.assert_called_once_with(
            "int-1",
            "siemens_m60",
            payload,
            1,
            correlation_id="corr-123",
            source="command",
            status_text_default="Command applied",
        )
        log_command.assert_called_once()
        command_audit = log_command.call_args.args[0]
        self.assertEqual("corr-123", command_audit.correlation_id)
        self.assertTrue(command_audit.allowed)
        self.assertTrue(command_audit.success)
        self.assertEqual("set_mode", command_audit.command_type)
        self.assertEqual(("corr-123", "command", payload), probe.status_log_calls[0])
        self.assertEqual(("int-1", "siemens_m60", payload), probe.cached_status)
        self.assertEqual("Command applied", probe.status_text)
        self.assertTrue(probe.is_online)
        self.assertEqual("v2c", probe.active_snmp_version)
        self.assertEqual("", probe.error)
        self.assertEqual("", probe.m60_status.get("status_text", ""))
        self.assertEqual("applied", probe.selected_controller_command_lifecycle["stage"])
        self.assertEqual("set_mode", probe.selected_controller_command_lifecycle["command_id"])
        self.assertEqual("corr-123", probe.selected_controller_command_lifecycle["correlation_id"])
        self.assertTrue(probe.selected_controller_command_lifecycle["acknowledged"])
        self.assertTrue(probe.selected_controller_command_lifecycle["is_terminal"])
        self.assertIn("Applied:", probe.selected_controller_command_lifecycle_notice)

    def test_command_state_send_command_preserves_verified_lifecycle_stage(self):
        probe = self._make_command_status_probe()
        probe.status_log_calls = []
        probe.write_unlock_until = probe._utc_future_iso(60)
        payload = {
            "is_online": True,
            "timestamp": "2026-05-27T00:00:03+00:00",
            "raw_data": {"active_message": "ROAD WORK AHEAD", "message_plan_active": True},
            "extra": {"dms": {"verification_outcome": "verified"}},
            "errors": [],
        }

        async def _fake_execute_command_result(device_type, config, cmd_type, value, safe_command_probe, device_id=""):
            return CommandExecutionResult(
                success=True,
                payload=payload,
                mp_model=1,
                error="",
                lifecycle_stage="verified",
                lifecycle_notice="Command verified.",
                acknowledged=True,
            )

        with patch("opensignal_its.states.command_state.uuid4", return_value=type("_Uuid", (), {"hex": "corr-789"})()), patch(
            "opensignal_its.states.command_state.CommandService.execute_command_result",
            side_effect=_fake_execute_command_result,
        ) as execute_command_result, patch(
            "opensignal_its.states.command_state.STORE.log_command",
        ):
            asyncio.run(probe.send_command("set_message", {"message": "ROAD WORK AHEAD", "activate_plan": True}))

        execute_command_result.assert_awaited_once()
        self.assertEqual("verified", probe.selected_controller_command_lifecycle["stage"])
        self.assertEqual("set_message", probe.selected_controller_command_lifecycle["command_id"])
        self.assertEqual("corr-789", probe.selected_controller_command_lifecycle["correlation_id"])
        self.assertTrue(probe.selected_controller_command_lifecycle["acknowledged"])
        self.assertTrue(probe.selected_controller_command_lifecycle["is_terminal"])
        self.assertIn("Verified:", probe.selected_controller_command_lifecycle_notice)

    def test_command_state_send_command_preserves_timed_out_lifecycle_stage(self):
        probe = self._make_command_status_probe()
        probe.status_text = "previous"
        probe.status_log_calls = []
        probe.write_unlock_until = probe._utc_future_iso(60)
        payload = {
            "is_online": True,
            "status_text": "Online - Pattern 1, Unit normal",
            "timestamp": "2026-05-27T00:00:04+00:00",
            "raw_data": {"current_pattern": "1", "unit_status": "normal"},
            "extra": {},
            "errors": [],
        }

        async def _fake_execute_command_result(device_type, config, cmd_type, value, safe_command_probe, device_id=""):
            return CommandExecutionResult(
                success=False,
                payload=payload,
                mp_model=1,
                error="Post-command verification timed out: requested traffic-signal pattern did not appear after poll.",
                lifecycle_stage="timed_out",
                lifecycle_notice="Post-command verification timed out: requested traffic-signal pattern did not appear after poll.",
                acknowledged=True,
            )

        with patch("opensignal_its.states.command_state.uuid4", return_value=type("_Uuid", (), {"hex": "corr-790"})()), patch(
            "opensignal_its.states.command_state.CommandService.execute_command_result",
            side_effect=_fake_execute_command_result,
        ) as execute_command_result, patch(
            "opensignal_its.states.command_state.STORE.log_command",
        ):
            asyncio.run(probe.send_command("select_pattern", 2))

        execute_command_result.assert_awaited_once()
        self.assertEqual("timed_out", probe.selected_controller_command_lifecycle["stage"])
        self.assertEqual("select_pattern", probe.selected_controller_command_lifecycle["command_id"])
        self.assertEqual("corr-790", probe.selected_controller_command_lifecycle["correlation_id"])
        self.assertTrue(probe.selected_controller_command_lifecycle["acknowledged"])
        self.assertTrue(probe.selected_controller_command_lifecycle["is_terminal"])
        self.assertIn("Timed Out:", probe.selected_controller_command_lifecycle_notice)

    def test_command_state_send_command_failure_keeps_failure_branch_behavior(self):
        probe = self._make_command_status_probe()
        probe.status_text = "previous"
        probe.status_log_calls = []
        probe.write_unlock_until = probe._utc_future_iso(60)
        payload = {
            "is_online": False,
            "status_text": "Command denied",
            "timestamp": "2026-05-27T00:00:04+00:00",
            "raw_data": {},
            "extra": {},
            "errors": [],
        }

        async def _fake_execute_command_result(device_type, config, cmd_type, value, safe_command_probe, device_id=""):
            return CommandExecutionResult(
                success=False,
                payload=payload,
                mp_model=1,
                error="Command failed",
                lifecycle_stage="failed",
                lifecycle_notice="Command failed",
                acknowledged=False,
            )

        with patch("opensignal_its.states.command_state.uuid4", return_value=type("_Uuid", (), {"hex": "corr-456"})()), patch(
            "opensignal_its.states.command_state.CommandService.execute_command_result",
            side_effect=_fake_execute_command_result,
        ) as execute_command_result, patch(
            "opensignal_its.states.command_state.STORE.log_command",
        ) as log_command, patch.object(
            type(probe),
            "_apply_selected_status_result",
            wraps=probe._apply_selected_status_result,
        ) as apply_selected_status_result:
            asyncio.run(probe.send_command("set_mode", "free"))

        execute_command_result.assert_awaited_once()
        apply_selected_status_result.assert_not_called()
        log_command.assert_called_once()
        self.assertEqual("Command failed", probe.error)
        self.assertFalse(probe.is_online)
        self.assertEqual("previous", probe.status_text)
        self.assertEqual(("int-1", "siemens_m60", payload), probe.cached_status)
        self.assertEqual([], probe.status_log_calls)
        self.assertEqual("failed", probe.selected_controller_command_lifecycle["stage"])
        self.assertEqual("set_mode", probe.selected_controller_command_lifecycle["command_id"])
        self.assertEqual("corr-456", probe.selected_controller_command_lifecycle["correlation_id"])
        self.assertFalse(probe.selected_controller_command_lifecycle["acknowledged"])
        self.assertTrue(probe.selected_controller_command_lifecycle["is_terminal"])
        self.assertIn("Failed:", probe.selected_controller_command_lifecycle_notice)

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
            "pending_command_correlation_id",
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
            "controller_profile_form_polling_enabled",
            "controller_profile_form_latitude_text",
            "controller_profile_form_longitude_text",
            "controller_profile_map_point_latitude_text",
            "controller_profile_map_point_longitude_text",
            "controller_profile_creation_dialog_open",
            "initialize_controller_profiles",
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
            "update_controller_profile_form_polling_enabled",
            "update_controller_profile_form_latitude_text",
            "update_controller_profile_form_longitude_text",
            "select_controller_profile_map_point",
            "set_controller_profile_creation_dialog_open",
            "open_controller_profile_creation_dialog",
            "close_controller_profile_creation_dialog",
            "new_controller_profile",
            "load_controller_profile",
            "load_controller_profile_from_row",
            "update_controller_profile_polling_enabled",
            "open_controller_profile_editor",
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
            "selected_controller_command_capabilities",
            "selected_controller_command_notice",
            "selected_controller_pattern_action_rows",
            "selected_controller_mode_action_rows",
            "selected_controller_supports_select_pattern",
            "selected_controller_supports_set_mode",
            "selected_controller_supports_manual_hold",
            "selected_controller_supports_advance_phase",
            "selected_controller_media_streams",
            "selected_controller_media_statuses",
            "selected_controller_media_rows",
            "selected_controller_media_notice",
            "selected_controller_media_loading",
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
            "sync_map_selection_from_storage",
            "_build_config",
            "_selected_device_target",
            "_apply_phase_payload",
            "_collect_selected_status_snapshot",
            "_apply_status_snapshot",
            "refresh_selected_controller_media_stream_health",
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
            "selected_controller_command_lifecycle",
            "selected_controller_command_lifecycle_notice",
            "_set_command_lifecycle_state",
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
            "fleet_unmapped_profile_rows",
            "fleet_map_data",
            "fleet_map_layout",
            "fleet_map_figure",
            "fleet_map_src_doc",
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
        self.assertTrue(TrafficState.auto_refresh_loop.is_background)

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
