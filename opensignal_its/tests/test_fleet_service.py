import unittest
import asyncio

from opensignal_its.models.device import DeviceConfig
from opensignal_its.models.fleet import FleetRefreshView, FleetSnapshotEntry, RuntimeRegistryView
from opensignal_its.services.fleet_service import FleetService


class FleetServiceTests(unittest.TestCase):
    def test_parse_profiles_json_returns_profiles(self):
        raw = '[{"device_id":"int-1","device_type":"siemens_m60","ip_address":"10.0.0.1"}]'
        profiles = FleetService.parse_profiles_json(raw)
        self.assertEqual(1, len(profiles))
        self.assertEqual("int-1", profiles[0]["device_id"])
        self.assertEqual("siemens_m60", profiles[0]["device_type"])

    def test_parse_profiles_json_rejects_non_list(self):
        with self.assertRaises(ValueError):
            FleetService.parse_profiles_json('{"device_id":"int-1"}')

    def test_upsert_profile_appends_new_profile(self):
        profiles = [{"device_id": "a", "device_type": "siemens_m60", "ip_address": "10.0.0.1"}]

        updated = FleetService.upsert_profile(
            profiles,
            {"device_id": "b", "device_type": "siemens_m60", "ip_address": "10.0.0.2"},
        )

        self.assertEqual(2, len(updated))
        self.assertEqual("b", updated[1]["device_id"])

    def test_upsert_profile_replaces_existing_profile(self):
        profiles = [{"device_id": "a", "device_type": "siemens_m60", "ip_address": "10.0.0.1"}]

        updated = FleetService.upsert_profile(
            profiles,
            {
                "device_id": "a",
                "device_type": "siemens_m60",
                "ip_address": "10.0.0.9",
                "name": "Updated A",
            },
        )

        self.assertEqual(1, len(updated))
        self.assertEqual("10.0.0.9", updated[0]["ip_address"])
        self.assertEqual("Updated A", updated[0]["name"])

    def test_remove_profile_drops_matching_device_id(self):
        profiles = [
            {"device_id": "a", "device_type": "siemens_m60", "ip_address": "10.0.0.1"},
            {"device_id": "b", "device_type": "siemens_m60", "ip_address": "10.0.0.2"},
        ]

        updated = FleetService.remove_profile(profiles, "a")

        self.assertEqual(1, len(updated))
        self.assertEqual("b", updated[0]["device_id"])

    def test_build_profile_rows_formats_compact_summary(self):
        rows = FleetService.build_profile_rows(
            [
                {
                    "device_id": "int-1",
                    "device_type": "siemens_m60",
                    "ip_address": "10.0.0.1",
                    "name": "Main & 1st",
                }
            ]
        )

        self.assertEqual(1, len(rows))
        self.assertIn("int-1 | 10.0.0.1 | siemens_m60", rows[0])
        self.assertIn("Main & 1st", rows[0])

    def test_filter_profiles_matches_device_id_name_and_ip(self):
        profiles = [
            {
                "device_id": "int-1",
                "device_type": "siemens_m60",
                "ip_address": "10.0.0.1",
                "name": "Main & 1st",
            },
            {
                "device_id": "int-2",
                "device_type": "siemens_m60",
                "ip_address": "10.0.0.2",
                "name": "Broadway",
            },
        ]

        self.assertEqual(["int-1"], [p["device_id"] for p in FleetService.filter_profiles(profiles, "main")])
        self.assertEqual(["int-2"], [p["device_id"] for p in FleetService.filter_profiles(profiles, "10.0.0.2")])
        self.assertEqual(["int-2"], [p["device_id"] for p in FleetService.filter_profiles(profiles, "int-2")])

    def test_sort_profiles_orders_by_name_and_ip(self):
        profiles = [
            {
                "device_id": "int-2",
                "device_type": "siemens_m60",
                "ip_address": "10.0.0.20",
                "name": "Zulu",
            },
            {
                "device_id": "int-1",
                "device_type": "siemens_m60",
                "ip_address": "10.0.0.3",
                "name": "Alpha",
            },
        ]

        by_name = FleetService.sort_profiles(profiles, "name")
        by_ip_desc = FleetService.sort_profiles(profiles, "ip_address", descending=True)

        self.assertEqual(["int-1", "int-2"], [p["device_id"] for p in by_name])
        self.assertEqual(["int-2", "int-1"], [p["device_id"] for p in by_ip_desc])

    def test_build_profile_display_rows_includes_status_metadata(self):
        profiles = [
            {"device_id": "int-1", "device_type": "siemens_m60", "ip_address": "10.0.0.1"},
            {"device_id": "int-2", "device_type": "siemens_m60", "ip_address": "10.0.0.2"},
            {"device_id": "int-3", "device_type": "siemens_m60", "ip_address": "10.0.0.3"},
        ]
        status_map = {
            "int-1": {"is_online": True},
            "int-2": {"is_online": False},
        }

        rows = FleetService.build_profile_display_rows(profiles, status_map)

        self.assertEqual("Online", rows[0]["status_label"])
        self.assertEqual("green", rows[0]["status_scheme"])
        self.assertEqual("No status detail.", rows[0]["detail_text"])
        self.assertEqual("", rows[0]["updated_text"])
        self.assertEqual("Offline", rows[1]["status_label"])
        self.assertEqual("red", rows[1]["status_scheme"])
        self.assertEqual("No status detail.", rows[1]["detail_text"])
        self.assertEqual("", rows[1]["updated_text"])
        self.assertEqual("Unknown", rows[2]["status_label"])
        self.assertEqual("gray", rows[2]["status_scheme"])
        self.assertEqual("No poll data yet.", rows[2]["detail_text"])
        self.assertEqual("", rows[2]["updated_text"])

    def test_build_profile_display_rows_uses_status_text_when_present(self):
        profiles = [{"device_id": "int-1", "device_type": "siemens_m60", "ip_address": "10.0.0.1"}]
        status_map = {"int-1": {"is_online": True, "status_text": "Pattern 2 | Unit Free"}}

        rows = FleetService.build_profile_display_rows(profiles, status_map)

        self.assertEqual("Pattern 2 | Unit Free", rows[0]["detail_text"])

    def test_build_profile_display_rows_formats_timestamp_when_present(self):
        profiles = [{"device_id": "int-1", "device_type": "siemens_m60", "ip_address": "10.0.0.1"}]
        status_map = {
            "int-1": {
                "is_online": True,
                "status_text": "Pattern 2 | Unit Free",
                "timestamp": "2026-05-23T12:34:56+00:00",
            }
        }

        rows = FleetService.build_profile_display_rows(profiles, status_map)

        self.assertEqual("Updated 2026-05-23 12:34:56+00:00", rows[0]["updated_text"])

    def test_build_profile_from_form_validates_and_normalizes(self):
        profile = FleetService.build_profile_from_form(
            device_id="int-1",
            name="Main & 1st",
            device_type="siemens_m60",
            ip_address_text="10.0.0.1",
            port_text="161",
            community="public",
            snmp_version="v1",
            timeout_text="3.5",
            retries_text="2",
        )

        self.assertEqual("int-1", profile["device_id"])
        self.assertEqual("10.0.0.1", profile["ip_address"])
        self.assertEqual(161, profile["port"])
        self.assertEqual(3.5, profile["timeout_seconds"])
        self.assertEqual(2, profile["retries"])

    def test_build_profile_from_form_rejects_invalid_port(self):
        with self.assertRaises(ValueError):
            FleetService.build_profile_from_form(
                device_id="int-1",
                name="",
                device_type="siemens_m60",
                ip_address_text="10.0.0.1",
                port_text="70000",
                community="public",
                snmp_version="v1",
                timeout_text="3",
                retries_text="1",
            )

    def test_build_profile_from_form_rejects_invalid_ip_address(self):
        with self.assertRaises(ValueError):
            FleetService.build_profile_from_form(
                device_id="int-1",
                name="",
                device_type="siemens_m60",
                ip_address_text="not-an-ip",
                port_text="161",
                community="public",
                snmp_version="v1",
                timeout_text="3",
                retries_text="1",
            )

    def test_select_profile_prefers_selected_id(self):
        profiles = [
            {"device_id": "a", "device_type": "siemens_m60", "ip_address": "10.0.0.1"},
            {"device_id": "b", "device_type": "siemens_m60", "ip_address": "10.0.0.2"},
        ]
        selected = FleetService.select_profile(profiles, "b")
        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual("b", selected["device_id"])

    def test_build_device_config_maps_profile_fields(self):
        profile = {
            "device_id": "int-1",
            "device_type": "siemens_m60",
            "ip_address": "10.0.0.1",
            "port": 1161,
            "community": "private",
            "snmp_version": "v1",
            "timeout_seconds": 2.5,
            "retries": 2,
            "name": "Intersection 1",
        }
        config = FleetService.build_device_config(profile)
        self.assertEqual("10.0.0.1", config.ip_address)
        self.assertEqual(1161, config.port)
        self.assertEqual("Intersection 1", config.name)

    def test_summarize_status_map_counts_online_offline(self):
        status_map = {
            "int-1": {"is_online": True, "status_text": "ok"},
            "int-2": {"is_online": False, "status_text": "down"},
            "int-3": {"is_online": True, "status_text": "ok"},
        }
        summary = FleetService.summarize_status_map(status_map)
        self.assertEqual(3, summary["total"])
        self.assertEqual(2, summary["online"])
        self.assertEqual(1, summary["offline"])

    def test_format_status_row(self):
        row = FleetService.format_status_row(
            "int-1",
            "siemens_m60",
            {"is_online": True, "status_text": "Online - Pattern 1"},
        )
        self.assertIn("int-1", row)
        self.assertIn("siemens_m60", row)
        self.assertIn("ONLINE", row)

    def test_resolve_target_uses_selected_profile(self):
        profiles = [
            {"device_id": "a", "device_type": "siemens_m60", "ip_address": "10.0.0.1"},
            {"device_id": "b", "device_type": "siemens_m60", "ip_address": "10.0.0.2"},
        ]
        fallback = DeviceConfig(ip_address="10.0.0.100")

        device_type, device_id, config = FleetService.resolve_target(
            profiles=profiles,
            selected_device_id="b",
            fallback_config=fallback,
            fallback_device_id="single",
        )

        self.assertEqual("siemens_m60", device_type)
        self.assertEqual("b", device_id)
        self.assertEqual("10.0.0.2", config.ip_address)

    def test_resolve_target_falls_back_when_profiles_empty(self):
        fallback = DeviceConfig(ip_address="10.0.0.100")

        device_type, device_id, config = FleetService.resolve_target(
            profiles=[],
            selected_device_id="",
            fallback_config=fallback,
            fallback_device_id="legacy-device",
            fallback_device_type="siemens_m60",
        )

        self.assertEqual("siemens_m60", device_type)
        self.assertEqual("legacy-device", device_id)
        self.assertEqual("10.0.0.100", config.ip_address)

    def test_build_snapshot_entry_success(self):
        entry = FleetService.build_snapshot_entry(
            device_id="int-1",
            device_type="siemens_m60",
            payload={"is_online": True, "status_text": "ok", "timestamp": "2026-05-23T00:00:00+00:00"},
            mp_model=1,
        )
        self.assertIsInstance(entry, FleetSnapshotEntry)
        self.assertEqual("int-1", entry.device_id)
        self.assertTrue(bool(entry.status.is_online))
        self.assertIn("ONLINE", entry.row)
        self.assertIsNotNone(entry.payload)

    def test_build_snapshot_entry_error(self):
        entry = FleetService.build_snapshot_entry(
            device_id="int-2",
            device_type="siemens_m60",
            payload=None,
            mp_model=1,
            error="connect timeout",
        )
        self.assertIsInstance(entry, FleetSnapshotEntry)
        self.assertEqual("int-2", entry.device_id)
        self.assertFalse(bool(entry.status.is_online))
        self.assertIn("ERROR", entry.row)
        self.assertIsNone(entry.payload)

    def test_compile_refresh_view_selects_matching_payload(self):
        entries = [
            FleetService.build_snapshot_entry(
                device_id="a",
                device_type="siemens_m60",
                payload={"is_online": True, "status_text": "ok-a", "timestamp": "t1"},
                mp_model=1,
            ),
            FleetService.build_snapshot_entry(
                device_id="b",
                device_type="siemens_m60",
                payload={"is_online": False, "status_text": "ok-b", "timestamp": "t2"},
                mp_model=0,
            ),
        ]
        view = FleetService.compile_refresh_view(entries, selected_device_id="b")
        self.assertIsInstance(view, FleetRefreshView)
        self.assertEqual(2, len(view.rows))
        self.assertIn("a", view.status_by_id)
        self.assertIn("b", view.status_by_id)
        assert view.selected_payload is not None
        self.assertEqual("ok-b", view.selected_payload["status_text"])
        self.assertEqual(0, int(view.selected_mp_model))

    def test_collect_refresh_view_builds_status_and_rows(self):
        profiles = [
            {"device_id": "a", "device_type": "siemens_m60", "ip_address": "10.0.0.1"},
            {"device_id": "b", "device_type": "siemens_m60", "ip_address": "10.0.0.2"},
        ]

        async def collector(device_type, config, device_id=""):
            if device_id == "a":
                return {"is_online": True, "status_text": "ok-a", "timestamp": "t1"}, 1
            raise RuntimeError("connect failed")

        view = asyncio.run(
            FleetService.collect_refresh_view(
                profiles=profiles,
                selected_device_id="a",
                collector=collector,
            )
        )

        self.assertIsInstance(view, FleetRefreshView)
        self.assertEqual("a", view.selected_device_id)
        self.assertEqual(2, len(view.rows))
        self.assertIn("a", view.status_by_id)
        self.assertIn("b", view.status_by_id)
        self.assertTrue(bool(view.selected_payload))

    def test_collect_refresh_view_selects_first_when_missing(self):
        profiles = [
            {"device_id": "a", "device_type": "siemens_m60", "ip_address": "10.0.0.1"},
            {"device_id": "b", "device_type": "siemens_m60", "ip_address": "10.0.0.2"},
        ]

        async def collector(device_type, config, device_id=""):
            return {"is_online": True, "status_text": f"ok-{device_id}", "timestamp": "t"}, 1

        view = asyncio.run(
            FleetService.collect_refresh_view(
                profiles=profiles,
                selected_device_id="missing",
                collector=collector,
            )
        )

        self.assertEqual("a", view.selected_device_id)
        assert view.selected_payload is not None
        self.assertEqual("ok-a", view.selected_payload["status_text"])

    def test_build_runtime_registry_view_formats_summary_and_rows(self):
        status = {
            "count": 2,
            "running_count": 1,
            "keys": ["siemens_m60::a", "siemens_m60::b"],
            "running_keys": ["siemens_m60::b"],
        }

        view = FleetService.build_runtime_registry_view(status)

        self.assertIsInstance(view, RuntimeRegistryView)
        self.assertIn("2 sites", view.summary)
        self.assertEqual(2, len(view.rows))
        self.assertIn("siemens_m60::a", view.rows[0])
        self.assertIn("siemens_m60::b (polling)", view.rows[1])

    def test_build_runtime_registry_view_handles_missing_fields(self):
        view = FleetService.build_runtime_registry_view({})

        self.assertEqual("Active poll sessions: 0 sites, 0 polling loops running.", view.summary)
        self.assertEqual([], view.rows)
        self.assertEqual(0, int(view.count))
        self.assertEqual(0, int(view.running_count))


if __name__ == "__main__":
    unittest.main()
