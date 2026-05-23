import unittest

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


if __name__ == "__main__":
    unittest.main()
