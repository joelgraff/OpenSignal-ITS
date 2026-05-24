import unittest

from opensignal_its.models.event import AlarmDisplayRow, EventDisplayView, TimelineDisplayRow
from opensignal_its.models.fleet import FleetDeviceStatus, FleetRefreshView, RuntimeRegistryView
from opensignal_its.states.event_state import _event_view_to_state_fields
from opensignal_its.states.polling_state import _runtime_registry_view_to_state_fields
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


if __name__ == "__main__":
    unittest.main()
