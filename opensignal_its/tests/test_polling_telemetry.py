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
from opensignal_its.protocols.snmp import SNMPClient
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
    def __init__(
        self,
        values: dict[str, str],
        raise_oids: set[str] | None = None,
        batch_fail_oids: set[str] | None = None,
        batch_outcomes: dict[tuple[str, ...], tuple[list[str | None], str | None]] | None = None,
    ):
        self.values = values
        self.raise_oids = set(raise_oids or set())
        self.batch_fail_oids = set(batch_fail_oids or set())
        self.batch_outcomes = dict(batch_outcomes or {})
        self.calls: list[str] = []
        self.single_calls: list[str] = []
        self.batch_calls: list[tuple[str, ...]] = []

    async def create_target(self):
        return object()

    async def get_oid(self, oid: str, mp_model: int, target=None):
        self.single_calls.append(oid)
        self.calls.append(oid)
        if oid in self.raise_oids:
            raise RuntimeError(f"simulated failure for {oid}")
        value = self.values.get(oid)
        if value is None:
            return None, "missing"
        return value, None

    async def get_oids(self, oids: list[str], mp_model: int, target=None):
        batch_oids = tuple(oids)
        self.batch_calls.append(batch_oids)
        self.calls.extend(batch_oids)

        if batch_oids in self.batch_outcomes:
            return self.batch_outcomes[batch_oids]

        for oid in batch_oids:
            if oid in self.batch_fail_oids:
                return [None for _ in batch_oids], f"simulated batch failure for {oid}"
            if oid in self.raise_oids:
                return [None for _ in batch_oids], f"simulated batch failure for {oid}"

        values: list[str | None] = []
        for oid in batch_oids:
            value = self.values.get(oid)
            values.append(value)

        if any(value is None for value in values):
            return values, "missing"
        return values, None


def _build_siemens_values(
    *,
    include_sys_descr: bool = True,
    include_vehicle_group_masks: bool = True,
    include_ped_group_masks: bool = True,
) -> dict[str, str]:
    values = {
        OID_CURRENT_PATTERN: "7",
        OID_UNIT_STATUS: "1",
        OID_RING_STATUS_TEMPLATE.format(ring=1): "0",
        OID_RING_STATUS_TEMPLATE.format(ring=2): "0",
        OID_PHASE_GREENS_GROUP_TEMPLATE.format(group=1): "1",
        OID_PHASE_GREENS_GROUP_TEMPLATE.format(group=2): "0",
        OID_PHASE_REDS_GROUP_TEMPLATE.format(group=1): "254",
        OID_PHASE_REDS_GROUP_TEMPLATE.format(group=2): "255",
    }

    if include_sys_descr:
        values[OID_SYS_DESCR] = "Siemens M60"

    if include_vehicle_group_masks:
        values[OID_PHASE_VEH_CALL_GROUP_TEMPLATE.format(group=1)] = "0"
        values[OID_PHASE_VEH_CALL_GROUP_TEMPLATE.format(group=2)] = "0"

    if include_ped_group_masks:
        values[OID_PHASE_PED_CALL_GROUP_TEMPLATE.format(group=1)] = "0"
        values[OID_PHASE_PED_CALL_GROUP_TEMPLATE.format(group=2)] = "0"

    for phase in range(1, 17):
        values[OID_PHASE_STATUS_TEMPLATE.format(phase=phase)] = "1" if phase == 1 else "4"
        values[OID_VEH_CALL_TEMPLATE.format(phase=phase)] = "0"
        values[OID_PED_CALL_TEMPLATE.format(phase=phase)] = "0"
        values[OID_TIME_REMAINING_TEMPLATE.format(phase=phase)] = str(30 + phase)
        values[OID_PHASE_MAX_GREEN_1_TEMPLATE.format(phase=phase)] = "60"

    return values


class SNMPClientBatchTests(unittest.TestCase):
    def test_get_oids_returns_successful_multi_oid_values(self):
        async def _fake_get_cmd(*_args, **_kwargs):
            return None, None, None, [(None, "alpha"), (None, "beta")]

        client = SNMPClient(DeviceConfig(ip_address="10.0.0.1", name="batch-test"))

        with patch("opensignal_its.protocols.snmp.get_cmd", side_effect=_fake_get_cmd):
            values, error = asyncio.run(
                client.get_oids(["1.2.3", "1.2.4"], mp_model=0, target=object())
            )

        self.assertEqual(["alpha", "beta"], values)
        self.assertIsNone(error)


class PollingTelemetryTests(unittest.TestCase):
    def setUp(self):
        PollingService.reset_runtime()
        PollingService.reset_poll_telemetry()

    def tearDown(self):
        PollingService.reset_runtime()
        PollingService.reset_poll_telemetry()

    def _poll_siemens(
        self,
        *,
        include_sys_descr: bool = True,
        include_vehicle_group_masks: bool = True,
        include_ped_group_masks: bool = True,
        raise_sys_descr: bool = False,
        batch_fail_oids: set[str] | None = None,
        batch_outcomes: dict[tuple[str, ...], tuple[list[str | None], str | None]] | None = None,
    ) -> tuple[object, _FakeSNMPClient, SiemensM60]:
        device, fake_client = self._make_siemens_device(
            include_sys_descr=include_sys_descr,
            include_vehicle_group_masks=include_vehicle_group_masks,
            include_ped_group_masks=include_ped_group_masks,
            raise_sys_descr=raise_sys_descr,
            batch_fail_oids=batch_fail_oids,
            batch_outcomes=batch_outcomes,
        )
        status = asyncio.run(device.poll())
        return status, fake_client, device

    def _make_siemens_device(
        self,
        *,
        include_sys_descr: bool = True,
        include_vehicle_group_masks: bool = True,
        include_ped_group_masks: bool = True,
        raise_sys_descr: bool = False,
        missing_max_green_phases: set[int] | None = None,
        raise_max_green_phases: set[int] | None = None,
        batch_fail_oids: set[str] | None = None,
        batch_outcomes: dict[tuple[str, ...], tuple[list[str | None], str | None]] | None = None,
    ) -> tuple[SiemensM60, _FakeSNMPClient]:
        config = DeviceConfig(ip_address="10.0.0.1", name="int-1")
        device = SiemensM60(config)
        fake_client = _FakeSNMPClient(
            _build_siemens_values(
                include_sys_descr=include_sys_descr,
                include_vehicle_group_masks=include_vehicle_group_masks,
                include_ped_group_masks=include_ped_group_masks,
            ),
            raise_oids={OID_SYS_DESCR} if raise_sys_descr else set(),
            batch_fail_oids=batch_fail_oids,
            batch_outcomes=batch_outcomes,
        )
        for phase in set(missing_max_green_phases or set()):
            fake_client.values.pop(OID_PHASE_MAX_GREEN_1_TEMPLATE.format(phase=phase), None)
        for phase in set(raise_max_green_phases or set()):
            fake_client.raise_oids.add(OID_PHASE_MAX_GREEN_1_TEMPLATE.format(phase=phase))
        device._snmp = fake_client
        return device, fake_client

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
        status, _fake_client, _device = self._poll_siemens()
        telemetry = PollingService.poll_telemetry("siemens_m60::int-1")

        self.assertTrue(status.is_online)
        self.assertEqual("Online - Pattern 7, Unit normal", status.status_text)
        self.assertEqual(1, telemetry["scopes"]["SiemensM60.poll"]["count"])
        self.assertGreater(telemetry["scopes"]["SiemensM60.poll"]["last_duration_seconds"], 0.0)

    def test_siemens_m60_connect_uses_batched_probe_when_both_values_available(self):
        device, fake_client = self._make_siemens_device()

        result = asyncio.run(device.connect())

        self.assertTrue(result)
        self.assertEqual("Connected via SNMP v1", device.status.status_text)
        self.assertEqual([(
            OID_SYS_DESCR,
            OID_CURRENT_PATTERN,
        )], fake_client.batch_calls)
        self.assertEqual([], fake_client.single_calls)
        self.assertEqual([OID_SYS_DESCR, OID_CURRENT_PATTERN], fake_client.calls)

    def test_siemens_m60_connect_succeeds_when_batched_probe_returns_only_one_value_via_fallback(self):
        device, fake_client = self._make_siemens_device(
            batch_outcomes={
                (OID_SYS_DESCR, OID_CURRENT_PATTERN): (["Siemens M60", None], None),
            },
        )

        result = asyncio.run(device.connect())

        self.assertTrue(result)
        self.assertEqual("Connected via SNMP v1", device.status.status_text)
        self.assertEqual(1, len(fake_client.batch_calls))
        self.assertEqual(4, len(fake_client.calls))
        self.assertEqual([OID_SYS_DESCR, OID_CURRENT_PATTERN, OID_SYS_DESCR, OID_CURRENT_PATTERN], fake_client.calls)
        self.assertEqual([OID_SYS_DESCR, OID_CURRENT_PATTERN], fake_client.single_calls)

    def test_siemens_m60_connect_fails_when_both_values_unavailable(self):
        device, fake_client = self._make_siemens_device(
            include_sys_descr=False,
            include_vehicle_group_masks=True,
            include_ped_group_masks=True,
        )
        fake_client.values.pop(OID_CURRENT_PATTERN, None)

        result = asyncio.run(device.connect())

        self.assertFalse(result)
        self.assertEqual("SNMPv1 connection failed", device.status.status_text)
        self.assertEqual([OID_SYS_DESCR, OID_CURRENT_PATTERN, OID_SYS_DESCR, OID_CURRENT_PATTERN], fake_client.calls)
        self.assertEqual([(
            OID_SYS_DESCR,
            OID_CURRENT_PATTERN,
        )], fake_client.batch_calls)
        self.assertEqual([OID_SYS_DESCR, OID_CURRENT_PATTERN], fake_client.single_calls)

    def test_siemens_m60_connect_batch_failure_falls_back_to_individual_reads(self):
        device, fake_client = self._make_siemens_device(
            batch_fail_oids={OID_SYS_DESCR},
        )

        result = asyncio.run(device.connect())

        self.assertTrue(result)
        self.assertEqual("Connected via SNMP v1", device.status.status_text)
        self.assertEqual(1, len(fake_client.batch_calls))
        self.assertEqual(4, len(fake_client.calls))
        self.assertEqual([OID_SYS_DESCR, OID_CURRENT_PATTERN, OID_SYS_DESCR, OID_CURRENT_PATTERN], fake_client.calls)
        self.assertEqual([OID_SYS_DESCR, OID_CURRENT_PATTERN], fake_client.single_calls)

    def test_siemens_m60_poll_uses_group_masks_when_available(self):
        status, fake_client, device = self._poll_siemens()
        telemetry = dict(status.extra["poll_telemetry"])

        self.assertEqual(OID_SYS_DESCR, fake_client.calls[0])
        self.assertEqual(61, len(fake_client.calls))
        self.assertEqual(5, len(fake_client.batch_calls))
        self.assertEqual(61, telemetry["object_count"])
        for phase in range(1, 17):
            self.assertNotIn(OID_VEH_CALL_TEMPLATE.format(phase=phase), fake_client.calls)
            self.assertNotIn(OID_PED_CALL_TEMPLATE.format(phase=phase), fake_client.calls)
        self.assertEqual(61, telemetry["request_count"])
        self.assertEqual(22, telemetry["round_trip_count"])
        self.assertEqual(
            [
                (
                    OID_CURRENT_PATTERN,
                    OID_UNIT_STATUS,
                ),
                (
                    OID_RING_STATUS_TEMPLATE.format(ring=1),
                    OID_RING_STATUS_TEMPLATE.format(ring=2),
                ),
                (
                    OID_PHASE_GREENS_GROUP_TEMPLATE.format(group=1),
                    OID_PHASE_GREENS_GROUP_TEMPLATE.format(group=2),
                    OID_PHASE_REDS_GROUP_TEMPLATE.format(group=1),
                    OID_PHASE_REDS_GROUP_TEMPLATE.format(group=2),
                    OID_PHASE_VEH_CALL_GROUP_TEMPLATE.format(group=1),
                    OID_PHASE_VEH_CALL_GROUP_TEMPLATE.format(group=2),
                    OID_PHASE_PED_CALL_GROUP_TEMPLATE.format(group=1),
                    OID_PHASE_PED_CALL_GROUP_TEMPLATE.format(group=2),
                ),
                tuple(OID_PHASE_STATUS_TEMPLATE.format(phase=phase) for phase in range(1, 17)),
                tuple(OID_TIME_REMAINING_TEMPLATE.format(phase=phase) for phase in range(1, 17)),
            ],
            fake_client.batch_calls,
        )
        self.assertEqual("Siemens M60", device._cached_sys_descr)
        self.assertEqual(
            {
                "identity": 3,
                "ring_status": 2,
                "group_masks": 8,
                "phase_grid": 48,
            },
            telemetry["sections"],
        )
        self.assertEqual(
            {
                "section_order": ["identity", "ring_status", "group_masks", "phase_grid"],
                "rings": 2,
                "groups": 2,
                "phases": 16,
                "reads_per_phase": 3,
                "expected_request_count": 61,
            },
            telemetry["poll_shape"],
        )

    def test_siemens_m60_poll_falls_back_when_group_masks_missing(self):
        status, fake_client, _device = self._poll_siemens(
            include_vehicle_group_masks=False,
            include_ped_group_masks=False,
        )
        telemetry = dict(status.extra["poll_telemetry"])

        self.assertEqual(5, len(fake_client.batch_calls))
        self.assertIn(OID_VEH_CALL_TEMPLATE.format(phase=1), fake_client.calls)
        self.assertIn(OID_PED_CALL_TEMPLATE.format(phase=1), fake_client.calls)
        self.assertEqual(95, telemetry["request_count"])
        self.assertEqual(64, telemetry["round_trip_count"])

    def test_siemens_m60_phase_output_equivalent_across_group_mask_and_fallback_paths(self):
        group_status, _group_client, _group_device = self._poll_siemens()
        fallback_status, _fallback_client, _fallback_device = self._poll_siemens(
            include_vehicle_group_masks=False,
            include_ped_group_masks=False,
        )

        self.assertEqual(group_status.extra["phase_summary"], fallback_status.extra["phase_summary"])
        self.assertEqual(group_status.extra["phases"], fallback_status.extra["phases"])
        self.assertEqual(group_status.raw_data["phase_status"], fallback_status.raw_data["phase_status"])
        self.assertEqual(group_status.raw_data["vehicle_calls"], fallback_status.raw_data["vehicle_calls"])
        self.assertEqual(group_status.raw_data["ped_calls"], fallback_status.raw_data["ped_calls"])
        self.assertEqual(group_status.status_text, fallback_status.status_text)

    def test_siemens_m60_warm_poll_reuses_cached_sys_descr_and_max_green_on_same_instance(self):
        first_status, fake_client, device = self._poll_siemens()
        first_payload = first_status.model_dump(mode="json")
        first_telemetry = dict(first_payload["extra"]["poll_telemetry"])

        self.assertEqual(61, first_telemetry["request_count"])
        self.assertEqual(22, first_telemetry["round_trip_count"])
        self.assertEqual("Siemens M60", device._cached_sys_descr)
        self.assertEqual({phase: 60 for phase in range(1, 17)}, device._cached_phase_max_green_1)
        self.assertEqual(5, len(fake_client.batch_calls))

        fake_client.calls.clear()
        fake_client.batch_calls.clear()
        second_status = asyncio.run(device.poll())
        second_payload = second_status.model_dump(mode="json")
        second_telemetry = dict(second_payload["extra"]["poll_telemetry"])

        self.assertEqual(44, second_telemetry["request_count"])
        self.assertEqual(5, second_telemetry["round_trip_count"])
        self.assertEqual(44, len(fake_client.calls))
        self.assertEqual(5, len(fake_client.batch_calls))
        self.assertNotIn(OID_SYS_DESCR, fake_client.calls)
        self.assertEqual(OID_CURRENT_PATTERN, fake_client.calls[0])
        for phase in range(1, 17):
            phase_max_green_oid = OID_PHASE_MAX_GREEN_1_TEMPLATE.format(phase=phase)
            self.assertNotIn(phase_max_green_oid, fake_client.calls)
        self.assertEqual(first_payload["extra"]["phase_max_green_1"], second_payload["extra"]["phase_max_green_1"])
        self.assertEqual(first_payload["extra"]["phases"], second_payload["extra"]["phases"])
        self.assertEqual(first_payload["raw_data"]["phase_max_green_1"], second_payload["raw_data"]["phase_max_green_1"])

    def test_siemens_m60_batched_warm_poll_matches_individual_read_fallback_output(self):
        batched_device, batched_client = self._make_siemens_device()
        fallback_device, fallback_client = self._make_siemens_device(
            batch_fail_oids={
                OID_CURRENT_PATTERN,
                OID_RING_STATUS_TEMPLATE.format(ring=1),
                OID_PHASE_GREENS_GROUP_TEMPLATE.format(group=1),
                OID_PHASE_STATUS_TEMPLATE.format(phase=1),
                OID_TIME_REMAINING_TEMPLATE.format(phase=1),
            },
        )

        asyncio.run(batched_device.poll())
        asyncio.run(fallback_device.poll())

        batched_client.calls.clear()
        batched_client.batch_calls.clear()
        fallback_client.calls.clear()
        fallback_client.batch_calls.clear()

        batched_status = asyncio.run(batched_device.poll())
        fallback_status = asyncio.run(fallback_device.poll())

        batched_payload = batched_status.model_dump(mode="json")
        fallback_payload = fallback_status.model_dump(mode="json")
        batched_telemetry = dict(batched_payload["extra"]["poll_telemetry"])
        fallback_telemetry = dict(fallback_payload["extra"]["poll_telemetry"])

        self.assertEqual(batched_status.status_text, fallback_status.status_text)
        self.assertEqual(batched_payload["extra"]["phase_summary"], fallback_payload["extra"]["phase_summary"])
        self.assertEqual(batched_payload["extra"]["phases"], fallback_payload["extra"]["phases"])
        self.assertEqual(batched_payload["extra"]["phase_max_green_1"], fallback_payload["extra"]["phase_max_green_1"])
        self.assertEqual(batched_payload["raw_data"]["current_pattern"], fallback_payload["raw_data"]["current_pattern"])
        self.assertEqual(batched_payload["raw_data"]["unit_status"], fallback_payload["raw_data"]["unit_status"])
        self.assertEqual(batched_payload["raw_data"]["ring_status"], fallback_payload["raw_data"]["ring_status"])
        self.assertEqual(
            batched_payload["raw_data"]["ring_status_summary"],
            fallback_payload["raw_data"]["ring_status_summary"],
        )
        self.assertEqual(batched_payload["raw_data"]["phase_status"], fallback_payload["raw_data"]["phase_status"])
        self.assertEqual(batched_payload["raw_data"]["vehicle_calls"], fallback_payload["raw_data"]["vehicle_calls"])
        self.assertEqual(batched_payload["raw_data"]["ped_calls"], fallback_payload["raw_data"]["ped_calls"])
        self.assertEqual(44, batched_telemetry["request_count"])
        self.assertEqual(44, fallback_telemetry["request_count"])
        self.assertEqual(5, batched_telemetry["round_trip_count"])
        self.assertGreater(fallback_telemetry["round_trip_count"], batched_telemetry["round_trip_count"])
        self.assertEqual(44, len(batched_client.calls))
        self.assertGreater(len(fallback_client.calls), len(batched_client.calls))
        self.assertEqual(5, len(batched_client.batch_calls))
        self.assertEqual(5, len(fallback_client.batch_calls))

    def test_siemens_m60_sys_descr_cache_is_instance_local(self):
        first_status, first_client, first_device = self._poll_siemens()
        second_status, second_client, second_device = self._poll_siemens()

        self.assertEqual("Siemens M60", first_device._cached_sys_descr)
        self.assertEqual("Siemens M60", second_device._cached_sys_descr)
        self.assertEqual(61, dict(first_status.extra["poll_telemetry"])["request_count"])
        self.assertEqual(61, dict(second_status.extra["poll_telemetry"])["request_count"])
        self.assertEqual(OID_SYS_DESCR, first_client.calls[0])
        self.assertEqual(OID_SYS_DESCR, second_client.calls[0])
        self.assertEqual({phase: 60 for phase in range(1, 17)}, first_device._cached_phase_max_green_1)
        self.assertEqual({phase: 60 for phase in range(1, 17)}, second_device._cached_phase_max_green_1)
        for phase in range(1, 17):
            phase_max_green_oid = OID_PHASE_MAX_GREEN_1_TEMPLATE.format(phase=phase)
            self.assertIn(phase_max_green_oid, first_client.calls)
            self.assertIn(phase_max_green_oid, second_client.calls)

    def test_siemens_m60_missing_or_failed_sys_descr_does_not_poison_cache(self):
        for case_name, kwargs in (
            ("missing", {"include_sys_descr": False}),
            ("failed", {"raise_sys_descr": True}),
        ):
            with self.subTest(case_name=case_name):
                status, fake_client, device = self._poll_siemens(**kwargs)

                self.assertIsNone(device._cached_sys_descr)
                self.assertEqual("Online - Pattern 7, Unit normal", status.status_text)
                self.assertTrue(status.is_online)

                fake_client.raise_oids.clear()
                fake_client.values[OID_SYS_DESCR] = "Siemens M60"
                fake_client.calls.clear()

                second_status = asyncio.run(device.poll())
                second_telemetry = dict(second_status.extra["poll_telemetry"])

                self.assertEqual(45, second_telemetry["request_count"])
                self.assertEqual(6, second_telemetry["round_trip_count"])
                self.assertEqual("Siemens M60", device._cached_sys_descr)
                self.assertEqual(OID_SYS_DESCR, fake_client.calls[0])

    def test_siemens_m60_missing_or_failed_phase_max_green_reads_do_not_poison_cache(self):
        device, fake_client = self._make_siemens_device(
            missing_max_green_phases={4},
            raise_max_green_phases={7},
        )

        first_status = asyncio.run(device.poll())
        first_payload = first_status.model_dump(mode="json")

        self.assertEqual(61, first_payload["extra"]["poll_telemetry"]["request_count"])
        self.assertEqual(22, first_payload["extra"]["poll_telemetry"]["round_trip_count"])
        self.assertTrue(first_status.is_online)
        self.assertEqual("Online - Pattern 7, Unit normal", first_status.status_text)
        self.assertNotIn(4, device._cached_phase_max_green_1)
        self.assertNotIn(7, device._cached_phase_max_green_1)
        self.assertEqual(
            {phase: 60 for phase in range(1, 17) if phase not in {4, 7}},
            device._cached_phase_max_green_1,
        )

        fake_client.calls.clear()
        fake_client.batch_calls.clear()
        fake_client.values[OID_PHASE_MAX_GREEN_1_TEMPLATE.format(phase=4)] = "60"
        fake_client.raise_oids.discard(OID_PHASE_MAX_GREEN_1_TEMPLATE.format(phase=7))

        second_status = asyncio.run(device.poll())
        second_payload = second_status.model_dump(mode="json")

        self.assertEqual(46, second_payload["extra"]["poll_telemetry"]["request_count"])
        self.assertEqual(7, second_payload["extra"]["poll_telemetry"]["round_trip_count"])
        self.assertEqual(46, len(fake_client.calls))
        self.assertEqual(5, len(fake_client.batch_calls))
        self.assertIn(OID_PHASE_MAX_GREEN_1_TEMPLATE.format(phase=4), fake_client.calls)
        self.assertIn(OID_PHASE_MAX_GREEN_1_TEMPLATE.format(phase=7), fake_client.calls)
        self.assertNotIn(OID_PHASE_MAX_GREEN_1_TEMPLATE.format(phase=1), fake_client.calls)
        self.assertEqual({phase: 60 for phase in range(1, 17)}, device._cached_phase_max_green_1)

    def test_siemens_m60_collect_snapshot_warm_reuses_cached_phase_max_green_and_connect_probe(self):
        config = DeviceConfig(ip_address="10.0.0.1", name="int-1")
        _runtime_key, device = RUNTIME.get_or_create(SiemensM60.device_type, config, device_id="int-1")
        fake_client = _FakeSNMPClient(_build_siemens_values())
        device._snmp = fake_client

        first_payload, _ = asyncio.run(
            PollingService.collect_snapshot(SiemensM60.device_type, config, device_id="int-1")
        )
        self.assertEqual(63, len(fake_client.calls))
        self.assertEqual(61, first_payload["extra"]["poll_telemetry"]["request_count"])
        self.assertEqual(22, first_payload["extra"]["poll_telemetry"]["round_trip_count"])
        self.assertEqual({phase: 60 for phase in range(1, 17)}, device._cached_phase_max_green_1)

        fake_client.calls.clear()
        fake_client.batch_calls.clear()
        fake_client.single_calls.clear()
        second_payload, _ = asyncio.run(
            PollingService.collect_snapshot(SiemensM60.device_type, config, device_id="int-1")
        )

        self.assertEqual(46, len(fake_client.calls))
        self.assertEqual(44, second_payload["extra"]["poll_telemetry"]["request_count"])
        self.assertEqual(5, second_payload["extra"]["poll_telemetry"]["round_trip_count"])
        self.assertEqual(6, len(fake_client.batch_calls))
        self.assertEqual(0, len(fake_client.single_calls))
        for phase in range(1, 17):
            self.assertNotIn(OID_PHASE_MAX_GREEN_1_TEMPLATE.format(phase=phase), fake_client.calls)
        self.assertEqual(first_payload["extra"]["phase_max_green_1"], second_payload["extra"]["phase_max_green_1"])
        self.assertEqual(first_payload["extra"]["phases"], second_payload["extra"]["phases"])


if __name__ == "__main__":
    unittest.main()