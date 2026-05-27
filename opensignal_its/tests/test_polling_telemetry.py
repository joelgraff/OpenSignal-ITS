import asyncio
import unittest
from unittest.mock import patch

import reflex as rx

from opensignal_its.devices.base import Device
from opensignal_its.devices.siemens_m60 import (
    OID_CURRENT_PATTERN,
    OID_PHASE_GREENS_GROUP_TEMPLATE,
    OID_PHASE_MAX_GREEN_1_TEMPLATE,
    OID_PHASE_PED_CALL_GROUP_TEMPLATE,
    OID_PED_CALL_TEMPLATE,
    OID_PHASE_REDS_GROUP_TEMPLATE,
    OID_PHASE_STATUS_TEMPLATE,
    OID_PHASE_VEH_CALL_GROUP_TEMPLATE,
    OID_VEH_CALL_TEMPLATE,
    OID_RING_STATUS_TEMPLATE,
    OID_SYS_DESCR,
    OID_TIME_REMAINING_TEMPLATE,
    OID_UNIT_STATUS,
    SiemensM60,
)
from opensignal_its.models.device import DeviceConfig, DeviceStatus
from opensignal_its.services.device_runtime_service import RUNTIME
from opensignal_its.services.polling_service import PollingService
from opensignal_its.states.fleet_state import FleetStateMixin


class _OverlapTelemetryDevice(Device):
    device_type = "telemetry_overlap"
    entered_event: asyncio.Event | None = None
    release_event: asyncio.Event | None = None

    async def connect(self) -> bool:
        self.status.is_online = True
        self.status.status_text = "connected"
        return True

    async def poll(self) -> DeviceStatus:
        if self.entered_event is None or self.release_event is None:
            raise RuntimeError("telemetry events were not configured")

        self.entered_event.set()
        await self.release_event.wait()
        self.status.is_online = True
        self.status.status_text = "polled"
        self.status.raw_data = {"poll_source": "overlap-test"}
        self.status.extra = {"poll_source": "overlap-test"}
        return self.status

    async def command(self, command: str, params: dict) -> bool:
        self.status.errors.append(f"unsupported command {command}")
        return False


class _FakeSNMPClient:
    def __init__(self, values: dict[str, str]):
        self.values = values

    async def create_target(self):
        return object()

    async def get_oid(self, oid: str, mp_model: int, target=None):
        value = self.values.get(oid)
        if value is None:
            return None, "missing"
        return value, None


def _build_siemens_values() -> dict[str, str]:
    values = {
        OID_SYS_DESCR: "Siemens M60",
        OID_CURRENT_PATTERN: "7",
        OID_UNIT_STATUS: "1",
        OID_RING_STATUS_TEMPLATE.format(ring=1): "0",
        OID_RING_STATUS_TEMPLATE.format(ring=2): "0",
        OID_PHASE_GREENS_GROUP_TEMPLATE.format(group=1): "1",
        OID_PHASE_GREENS_GROUP_TEMPLATE.format(group=2): "0",
        OID_PHASE_REDS_GROUP_TEMPLATE.format(group=1): "254",
        OID_PHASE_REDS_GROUP_TEMPLATE.format(group=2): "255",
        OID_PHASE_VEH_CALL_GROUP_TEMPLATE.format(group=1): "0",
        OID_PHASE_VEH_CALL_GROUP_TEMPLATE.format(group=2): "0",
        OID_PHASE_PED_CALL_GROUP_TEMPLATE.format(group=1): "0",
        OID_PHASE_PED_CALL_GROUP_TEMPLATE.format(group=2): "0",
    }

    for phase in range(1, 17):
        values[OID_PHASE_STATUS_TEMPLATE.format(phase=phase)] = "1" if phase == 1 else "4"
        values[OID_VEH_CALL_TEMPLATE.format(phase=phase)] = "0"
        values[OID_PED_CALL_TEMPLATE.format(phase=phase)] = "0"
        values[OID_TIME_REMAINING_TEMPLATE.format(phase=phase)] = str(30 + phase)
        values[OID_PHASE_MAX_GREEN_1_TEMPLATE.format(phase=phase)] = "60"

    return values


class PollingTelemetryTests(unittest.TestCase):
    def setUp(self):
        PollingService.reset_runtime()
        PollingService.reset_poll_telemetry()

    def tearDown(self):
        PollingService.reset_runtime()
        PollingService.reset_poll_telemetry()

    def test_collect_snapshot_records_overlap_while_background_poll_is_active(self):
        async def _scenario() -> dict[str, object]:
            entered_event = asyncio.Event()
            release_event = asyncio.Event()
            _OverlapTelemetryDevice.entered_event = entered_event
            _OverlapTelemetryDevice.release_event = release_event

            config = DeviceConfig(ip_address="10.0.0.1", name="Overlap")
            runtime_key, device = RUNTIME.get_or_create(
                _OverlapTelemetryDevice.device_type,
                config,
                device_id="dev-1",
            )

            await device.start_polling(interval_seconds=9999)
            await asyncio.wait_for(entered_event.wait(), timeout=1)

            collect_task = asyncio.create_task(
                PollingService.collect_snapshot(
                    _OverlapTelemetryDevice.device_type,
                    config,
                    device_id="dev-1",
                )
            )
            await asyncio.sleep(0)

            live_snapshot = PollingService.poll_telemetry(runtime_key)
            self.assertEqual(2, live_snapshot["active_refresh_count"])
            self.assertEqual(1, live_snapshot["scopes"]["Device.start_polling"]["count"])
            self.assertEqual(1, live_snapshot["scopes"]["PollingService.collect_snapshot"]["count"])
            self.assertTrue(live_snapshot["scopes"]["PollingService.collect_snapshot"]["last_overlap_detected"])
            self.assertEqual(1, live_snapshot["scopes"]["PollingService.collect_snapshot"]["last_in_flight_before_start"])

            release_event.set()
            payload, mp_model = await asyncio.wait_for(collect_task, timeout=1)
            self.assertEqual("polled", payload["status_text"])
            self.assertEqual(1, mp_model)

            device.stop_polling()
            await asyncio.sleep(0)

            return PollingService.poll_telemetry(runtime_key)

        final_snapshot = asyncio.run(_scenario())

        self.assertEqual(0, final_snapshot["active_refresh_count"])
        self.assertGreater(final_snapshot["scopes"]["Device.start_polling"]["last_duration_seconds"], 0.0)
        self.assertGreater(final_snapshot["scopes"]["PollingService.collect_snapshot"]["last_duration_seconds"], 0.0)

    def test_refresh_fleet_status_records_fleet_boundary_timing(self):
        class _FleetTelemetryProbe(FleetStateMixin, rx.State):
            device_profiles_json: str = """[
                {
                    "device_id": "int-1",
                    "device_type": "siemens_m60",
                    "ip_address": "10.0.0.1"
                }
            ]"""
            selected_device_id: str = "int-1"
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
            fleet_status_summary: str = ""
            fleet_online_count: int = 0
            fleet_offline_count: int = 0
            fleet_total_count: int = 0
            error: str = ""
            status_text: str = ""
            is_online: bool = False
            last_updated: str = ""
            controller_profile_rows: list[dict[str, str]] = []
            controller_profile_notice: str = ""
            runtime_registry_refreshed: bool = False
            applied_snapshot: tuple[dict, int] | None = None
            cached_device_status: tuple[str, str, dict] | None = None

            def refresh_runtime_registry_status(self):
                self.runtime_registry_refreshed = True

            def _apply_status_snapshot(self, payload: dict, mp_model: int):
                self.applied_snapshot = (payload, mp_model)

            def _cache_device_status(self, device_id: str, device_type: str, payload: dict):
                self.cached_device_status = (device_id, device_type, payload)

            def _sync_controller_profile_rows(self):
                self.controller_profile_rows = [{"device_id": "int-1"}]
                self.controller_profile_notice = "synced"

        probe = _FleetTelemetryProbe(_reflex_internal_init=True)

        async def _fake_collect_snapshot(device_type, config, device_id=""):
            return (
                {
                    "device_id": device_id,
                    "is_online": True,
                    "status_text": "ok",
                    "timestamp": "2026-05-27T00:00:00+00:00",
                    "raw_data": {},
                    "extra": {},
                    "errors": [],
                },
                1,
            )

        with patch("opensignal_its.states.fleet_state.PollingService.collect_snapshot", side_effect=_fake_collect_snapshot), patch(
            "opensignal_its.states.fleet_state.PollingService.sync_runtime_registry",
            return_value=[],
        ):
            asyncio.run(probe.refresh_fleet_status())

        fleet_snapshot = PollingService.poll_telemetry("fleet::refresh")
        self.assertEqual(1, fleet_snapshot["scopes"]["FleetStateMixin.refresh_fleet_status"]["count"])
        self.assertGreater(fleet_snapshot["scopes"]["FleetStateMixin.refresh_fleet_status"]["last_duration_seconds"], 0.0)

    def test_siemens_m60_poll_records_driver_boundary_timing(self):
        config = DeviceConfig(ip_address="10.0.0.1", name="int-1")
        device = SiemensM60(config)
        device._snmp = _FakeSNMPClient(_build_siemens_values())

        status = asyncio.run(device.poll())
        telemetry = PollingService.poll_telemetry("siemens_m60::int-1")

        self.assertTrue(status.is_online)
        self.assertEqual("Online - Pattern 7, Unit normal", status.status_text)
        self.assertEqual(1, telemetry["scopes"]["SiemensM60.poll"]["count"])
        self.assertGreater(telemetry["scopes"]["SiemensM60.poll"]["last_duration_seconds"], 0.0)


if __name__ == "__main__":
    unittest.main()