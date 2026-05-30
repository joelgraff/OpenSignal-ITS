import asyncio
import unittest

from opensignal_its.models.device import DeviceConfig
from opensignal_its.services.snmp_compatibility_service import (
    PROBE_OID_SPECS,
    SnmpCompatibilityService,
)


def _oid_for(key: str) -> str:
    for spec in PROBE_OID_SPECS:
        if spec["key"] == key:
            return spec["oid"]
    raise AssertionError(f"Unknown probe key: {key}")


class SnmpCompatibilityServiceTests(unittest.TestCase):
    def _config(self) -> DeviceConfig:
        return DeviceConfig(ip_address="10.0.0.50", name="M50 candidate")

    def test_probe_reports_no_snmp_response(self):
        async def _fake_probe(oid: str, mp_model: int) -> tuple[str | None, str | None]:
            return None, "timeout"

        report = asyncio.run(
            SnmpCompatibilityService.probe_controller(
                self._config(),
                versions=["v1"],
                probe=_fake_probe,
            )
        )

        self.assertEqual(
            "Target did not respond even to standard SNMP sysDescr. Verify SNMP enablement, version, community, modem/NAT, firewall rules, and UDP/161 reachability before changing OID profiles.",
            report["summary"],
        )
        self.assertEqual(
            "Treat this as connectivity or SNMP-agent setup first; an M50-specific OID profile cannot work until basic SNMP responds.",
            report["recommendation"],
        )
        self.assertFalse(report["versions"][0]["standard_snmp_ready"])
        self.assertFalse(report["versions"][0]["m60_sepac_ready"])
        self.assertFalse(report["versions"][0]["ntcip_1202_ready"])

    def test_probe_distinguishes_ntcip_surface_without_m60_sepac_objects(self):
        responses = {
            (0, _oid_for("sys_descr")): "M50 controller",
            (0, _oid_for("ntcip_phase_greens_group_1")): "1",
        }

        async def _fake_probe(oid: str, mp_model: int) -> tuple[str | None, str | None]:
            value = responses.get((mp_model, oid))
            return (value, None) if value is not None else (None, "noSuchName")

        report = asyncio.run(
            SnmpCompatibilityService.probe_controller(
                self._config(),
                versions=["v1"],
                probe=_fake_probe,
            )
        )

        version = report["versions"][0]
        self.assertTrue(version["standard_snmp_ready"])
        self.assertFalse(version["m60_sepac_ready"])
        self.assertTrue(version["ntcip_1202_ready"])
        self.assertEqual(
            "Target exposes NTCIP objects but not the M60/SEPAC surface. Build or select a model-specific OID profile.",
            report["summary"],
        )

    def test_probe_reports_m60_sepac_compatibility_when_private_objects_respond(self):
        responses = {
            (0, _oid_for("sys_descr")): "Siemens M60",
            (0, _oid_for("m60_current_pattern")): "7",
        }

        async def _fake_probe(oid: str, mp_model: int) -> tuple[str | None, str | None]:
            value = responses.get((mp_model, oid))
            return (value, None) if value is not None else (None, "noSuchName")

        report = asyncio.run(
            SnmpCompatibilityService.probe_controller(
                self._config(),
                versions=["v1"],
                probe=_fake_probe,
            )
        )

        version = report["versions"][0]
        self.assertTrue(version["standard_snmp_ready"])
        self.assertTrue(version["m60_sepac_ready"])
        self.assertEqual(
            "At least one SNMP version exposes the M60/SEPAC surface expected by the current poller.",
            report["summary"],
        )
        self.assertEqual(
            "Set the controller profile snmp_version to v1 for the current M60/SEPAC poller.",
            report["recommendation"],
        )

    def test_probe_reports_m60_v1_ready_when_v2c_is_silent(self):
        responses = {
            (0, _oid_for("sys_descr")): "SEPAC 5.2.0   (JUN 2019), NTCIP Class B",
            (0, _oid_for("m60_current_pattern")): "2",
            (0, _oid_for("m60_unit_status")): "1",
            (0, _oid_for("ntcip_phase_greens_group_1")): "0",
            (0, _oid_for("ntcip_phase_reds_group_1")): "58",
        }

        async def _fake_probe(oid: str, mp_model: int) -> tuple[str | None, str | None]:
            value = responses.get((mp_model, oid))
            return (value, None) if value is not None else (None, "timeout")

        report = asyncio.run(
            SnmpCompatibilityService.probe_controller(
                self._config(),
                versions=["v1", "v2c"],
                probe=_fake_probe,
            )
        )

        v1_result, v2c_result = report["versions"]
        self.assertTrue(v1_result["m60_sepac_ready"])
        self.assertTrue(v1_result["ntcip_1202_ready"])
        self.assertFalse(v2c_result["standard_snmp_ready"])
        self.assertFalse(v2c_result["m60_sepac_ready"])
        self.assertEqual(
            "Set the controller profile snmp_version to v1 for the current M60/SEPAC poller.",
            report["recommendation"],
        )

    def test_normalize_versions_expands_auto_without_duplicates(self):
        self.assertEqual(["v1", "v2c"], SnmpCompatibilityService.normalize_versions(["auto", "v1"]))


if __name__ == "__main__":
    unittest.main()