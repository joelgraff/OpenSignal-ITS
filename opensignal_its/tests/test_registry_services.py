import asyncio
import json
import unittest
from datetime import datetime, timezone
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import AsyncMock, patch

from opensignal_its.devices.base import Device
from opensignal_its.devices.siemens_m60 import SiemensM60
from opensignal_its.models.device import DeviceConfig, DeviceStatus
from opensignal_its.db.audit_store import AuditStore
from opensignal_its.services.command_service import CommandService
from opensignal_its.services.device_runtime_service import DeviceRuntimeService, _RuntimeEntry
from opensignal_its.services.polling_service import PollingService


class _FakeRegistryDevice(Device):
    device_type = "fake_registry"

    async def connect(self) -> bool:
        self.status.timestamp = datetime(2000, 1, 1, tzinfo=timezone.utc)
        self.status.is_online = True
        self.status.status_text = "connected"
        return True

    async def poll(self) -> DeviceStatus:
        self.status.timestamp = datetime(2000, 1, 1, tzinfo=timezone.utc)
        self.status.is_online = True
        self.status.status_text = "polled"
        self.status.raw_data = {
            "current_pattern": "1",
            "unit_status": "normal",
            "instance_id": str(id(self)),
        }
        self.status.extra = {"phase_summary": {"green": [1], "yellow": [], "red": []}}
        return self.status

    async def command(self, command: str, params: dict) -> bool:
        if command == "set_mode":
            self.status.status_text = f"mode={params.get('mode', 'unknown')}"
            return True
        self.status.errors.append(f"unsupported command {command}")
        return False


class _StopTrackingDevice:
    def __init__(self):
        self.stopped = False

    def stop_polling(self):
        self.stopped = True


class _CapturingCommandDevice(Device):
    device_type = "fake_registry"

    def __init__(self, config: DeviceConfig):
        super().__init__(config)
        self.command_calls: list[tuple[str, dict[str, object]]] = []

    async def connect(self) -> bool:
        self.status.timestamp = datetime(2000, 1, 1, tzinfo=timezone.utc)
        self.status.is_online = True
        self.status.status_text = "connected"
        return True

    async def poll(self) -> DeviceStatus:
        self.status.timestamp = datetime(2000, 1, 1, tzinfo=timezone.utc)
        self.status.is_online = True
        self.status.status_text = "polled"
        return self.status

    async def command(self, command: str, params: dict) -> bool:
        self.command_calls.append((command, dict(params)))
        return True


class RegistryServicesTests(unittest.TestCase):
    def setUp(self):
        PollingService.reset_runtime()

    def tearDown(self):
        PollingService.reset_runtime()

    def test_polling_service_collect_snapshot_uses_registry(self):
        config = DeviceConfig(ip_address="10.0.0.1", name="Fake")

        payload, mp_model = asyncio.run(
            PollingService.collect_snapshot("fake_registry", config, device_id="dev-1")
        )

        self.assertTrue(payload["is_online"])
        self.assertEqual("polled", payload["status_text"])
        self.assertFalse(str(payload["timestamp"]).startswith("2000-01-01T00:00:00"))
        self.assertEqual(1, mp_model)

    def test_polling_service_collect_connection_status_uses_connect_only(self):
        config = DeviceConfig(ip_address="10.0.0.1", name="Fake")

        payload, mp_model = asyncio.run(
            PollingService.collect_connection_status("fake_registry", config, device_id="dev-1")
        )

        self.assertTrue(payload["is_online"])
        self.assertEqual("connected", payload["status_text"])
        self.assertFalse(str(payload["timestamp"]).startswith("2000-01-01T00:00:00"))
        self.assertEqual(1, mp_model)

    def test_command_service_execute_command_uses_registry(self):
        config = DeviceConfig(ip_address="10.0.0.1", name="Fake")

        success, payload, mp_model, error = asyncio.run(
            CommandService.execute_command(
                device_type="fake_registry",
                config=config,
                cmd_type="set_mode",
                value="coordinated",
                safe_command_probe=True,
                device_id="dev-1",
            )
        )

        self.assertTrue(success)
        self.assertEqual("polled", payload["status_text"])
        self.assertEqual("", error)
        self.assertEqual(1, mp_model)

    def test_command_service_execute_command_result_reports_applied_lifecycle(self):
        config = DeviceConfig(ip_address="10.0.0.1", name="Fake")

        result = asyncio.run(
            CommandService.execute_command_result(
                device_type="fake_registry",
                config=config,
                cmd_type="set_mode",
                value="coordinated",
                safe_command_probe=True,
                device_id="dev-1",
            )
        )

        self.assertTrue(result.success)
        self.assertEqual("applied", result.lifecycle_stage)
        self.assertEqual("Command applied.", result.lifecycle_notice)
        self.assertTrue(result.acknowledged)

    def test_command_service_select_pattern_reports_verified_lifecycle_when_poll_matches(self):
        config = DeviceConfig(ip_address="10.0.0.1", name="M60")
        device = SiemensM60(config)
        verified_status = DeviceStatus(
            device_id="int-1",
            is_online=True,
            status_text="Online - Pattern 2, Unit normal",
            raw_data={"current_pattern": "2", "unit_status": "normal"},
            extra={},
            errors=[],
        )

        with patch(
            "opensignal_its.services.command_service.RUNTIME.get_or_create",
            return_value=("siemens_m60::int-1", device),
        ), patch.object(device, "connect", new=AsyncMock(return_value=True)), patch.object(
            device,
            "command",
            new=AsyncMock(return_value=True),
        ), patch.object(device, "poll", new=AsyncMock(return_value=verified_status)):
            result = asyncio.run(
                CommandService.execute_command_result(
                    device_type="siemens_m60",
                    config=config,
                    cmd_type="select_pattern",
                    value=2,
                    safe_command_probe=False,
                    device_id="int-1",
                )
            )

        self.assertTrue(result.success)
        self.assertEqual("verified", result.lifecycle_stage)
        self.assertEqual("Command verified.", result.lifecycle_notice)
        self.assertTrue(result.acknowledged)
        self.assertEqual("2", result.payload["raw_data"]["current_pattern"])

    def test_command_service_select_pattern_reports_timed_out_when_poll_mismatches(self):
        config = DeviceConfig(ip_address="10.0.0.1", name="M60")
        device = SiemensM60(config)
        stale_status = DeviceStatus(
            device_id="int-1",
            is_online=True,
            status_text="Online - Pattern 1, Unit normal",
            raw_data={"current_pattern": "1", "unit_status": "normal"},
            extra={},
            errors=[],
        )

        with patch(
            "opensignal_its.services.command_service.RUNTIME.get_or_create",
            return_value=("siemens_m60::int-1", device),
        ), patch.object(device, "connect", new=AsyncMock(return_value=True)), patch.object(
            device,
            "command",
            new=AsyncMock(return_value=True),
        ), patch.object(device, "poll", new=AsyncMock(return_value=stale_status)):
            result = asyncio.run(
                CommandService.execute_command_result(
                    device_type="siemens_m60",
                    config=config,
                    cmd_type="select_pattern",
                    value=2,
                    safe_command_probe=False,
                    device_id="int-1",
                )
            )

        self.assertFalse(result.success)
        self.assertEqual("timed_out", result.lifecycle_stage)
        self.assertTrue(result.acknowledged)
        self.assertEqual(
            "Post-command verification timed out: requested traffic-signal pattern did not appear after poll.",
            result.error,
        )
        self.assertEqual("1", result.payload["raw_data"]["current_pattern"])

    def test_command_service_returns_unknown_command_error(self):
        config = DeviceConfig(ip_address="10.0.0.1", name="Fake")

        success, _payload, _mp_model, error = asyncio.run(
            CommandService.execute_command(
                device_type="fake_registry",
                config=config,
                cmd_type="unsupported",
                value=True,
                safe_command_probe=True,
                device_id="dev-1",
            )
        )

        self.assertFalse(success)
        self.assertIn("Unknown command", error)

    def test_command_service_execute_command_result_reports_failed_lifecycle(self):
        config = DeviceConfig(ip_address="10.0.0.1", name="Fake")

        result = asyncio.run(
            CommandService.execute_command_result(
                device_type="fake_registry",
                config=config,
                cmd_type="unsupported",
                value=True,
                safe_command_probe=True,
                device_id="dev-1",
            )
        )

        self.assertFalse(result.success)
        self.assertEqual("failed", result.lifecycle_stage)
        self.assertIn("Unknown command", result.lifecycle_notice)
        self.assertFalse(result.acknowledged)

    def test_command_service_shapes_manual_hold_params_explicitly(self):
        config = DeviceConfig(ip_address="10.0.0.1", name="Fake")
        device = _CapturingCommandDevice(config)

        with patch(
            "opensignal_its.services.command_service.RUNTIME.get_or_create",
            return_value=("fake_registry::dev-1", device),
        ):
            success, payload, mp_model, error = asyncio.run(
                CommandService.execute_command(
                    device_type="fake_registry",
                    config=config,
                    cmd_type="manual_hold",
                    value="true",
                    safe_command_probe=False,
                    device_id="dev-1",
                )
            )

        self.assertTrue(success)
        self.assertEqual("", error)
        self.assertEqual(1, mp_model)
        self.assertEqual("polled", payload["status_text"])
        self.assertEqual(
            [("manual_hold", {"hold": True, "probe_only": False, "allow_all_phases": True})],
            device.command_calls,
        )

    def test_command_service_shapes_advance_phase_params_explicitly(self):
        config = DeviceConfig(ip_address="10.0.0.1", name="Fake")
        device = _CapturingCommandDevice(config)

        with patch(
            "opensignal_its.services.command_service.RUNTIME.get_or_create",
            return_value=("fake_registry::dev-1", device),
        ):
            success, payload, mp_model, error = asyncio.run(
                CommandService.execute_command(
                    device_type="fake_registry",
                    config=config,
                    cmd_type="advance_phase",
                    value=True,
                    safe_command_probe=False,
                    device_id="dev-1",
                )
            )

        self.assertTrue(success)
        self.assertEqual("", error)
        self.assertEqual(1, mp_model)
        self.assertEqual("polled", payload["status_text"])
        self.assertEqual(
            [("advance_phase", {"probe_only": False, "allow_all_phases": True})],
            device.command_calls,
        )

    def test_siemens_m60_capabilities_expose_json_safe_command_metadata(self):
        config = DeviceConfig(ip_address="10.0.0.1", name="M60")

        capabilities = json.loads(json.dumps(SiemensM60(config).get_capabilities()))
        command_capabilities = capabilities["command_capabilities"]
        select_pattern = command_capabilities[0]
        set_mode = command_capabilities[1]
        manual_hold = command_capabilities[2]
        advance_phase = command_capabilities[3]

        self.assertEqual("traffic_signal_controller", capabilities["device_family"])
        self.assertEqual("ntcip", capabilities["protocol_family"])
        self.assertEqual(
            ["select_pattern", "set_mode", "manual_hold", "advance_phase"],
            [item["command_id"] for item in command_capabilities],
        )
        self.assertTrue(select_pattern["requires_confirmation"])
        self.assertEqual("integer", select_pattern["value_type"])
        self.assertEqual([1, 2], select_pattern["allowed_values"])
        self.assertEqual(
            [
                {"value": 1, "label": "Pattern 1"},
                {"value": 2, "label": "Pattern 2"},
            ],
            select_pattern["options"],
        )
        self.assertEqual("string", set_mode["value_type"])
        self.assertEqual(["free", "coordinated"], set_mode["allowed_values"])
        self.assertEqual(
            [
                {"value": "free", "label": "Free"},
                {"value": "coordinated", "label": "Coord"},
            ],
            set_mode["options"],
        )
        self.assertEqual("boolean", manual_hold["value_type"])
        self.assertEqual([True, False], manual_hold["allowed_values"])
        self.assertFalse(advance_phase["requires_value"])
        self.assertEqual("none", advance_phase["value_type"])

    def test_device_registry_supports_skyline_dms_emulator_capabilities(self):
        config = DeviceConfig(ip_address="10.0.1.20", name="Skyline DMS")

        device = Device.create("skyline_dms_emulator", config)
        capabilities = json.loads(json.dumps(device.get_capabilities()))
        command_capabilities = capabilities["command_capabilities"]

        self.assertEqual("SkylineDmsEmulator", device.__class__.__name__)
        self.assertIn("skyline_dms_emulator", Device.registered_types())
        self.assertEqual("dynamic_message_sign", capabilities["device_family"])
        self.assertEqual("ntcip", capabilities["protocol_family"])
        self.assertEqual(["set_message"], [item["command_id"] for item in command_capabilities])
        self.assertEqual("object", command_capabilities[0]["value_type"])
        self.assertEqual(
            {
                "type": "object",
                "required": ["message"],
                "properties": {
                    "message": {"type": "string", "min_length": 1, "max_length": 120},
                    "activate_plan": {"type": "boolean"},
                },
            },
            command_capabilities[0]["value_schema"],
        )

    def test_command_service_execute_command_result_applies_dms_message(self):
        config = DeviceConfig(ip_address="10.0.1.20", name="Skyline DMS")

        result = asyncio.run(
            CommandService.execute_command_result(
                device_type="skyline_dms_emulator",
                config=config,
                cmd_type="set_message",
                value={"message": "ROAD WORK AHEAD", "activate_plan": True},
                safe_command_probe=False,
                device_id="dms-1",
            )
        )

        self.assertTrue(result.success)
        self.assertEqual("verified", result.lifecycle_stage)
        self.assertEqual("Command verified.", result.lifecycle_notice)
        self.assertTrue(result.acknowledged)
        self.assertEqual("ROAD WORK AHEAD", result.payload["raw_data"]["active_message"])
        self.assertTrue(result.payload["raw_data"]["message_plan_active"])
        self.assertEqual("Skyline DMS emulator", result.payload["extra"]["dms"]["target"])
        self.assertEqual("verified", result.payload["extra"]["dms"]["verification_outcome"])

    def test_command_service_validates_dms_message_schema(self):
        config = DeviceConfig(ip_address="10.0.1.20", name="Skyline DMS")

        result = asyncio.run(
            CommandService.execute_command_result(
                device_type="skyline_dms_emulator",
                config=config,
                cmd_type="set_message",
                value={"message": "   ", "activate_plan": True},
                safe_command_probe=False,
                device_id="dms-1",
            )
        )

        self.assertFalse(result.success)
        self.assertEqual("failed", result.lifecycle_stage)
        self.assertEqual("set_message message is required.", result.error)
        self.assertFalse(result.acknowledged)

    def test_command_service_reports_failed_dms_verification_mismatch(self):
        config = DeviceConfig(ip_address="10.0.1.20", name="Skyline DMS")
        device = Device.create("skyline_dms_emulator", config)
        device._verification_mode = "activation_mismatch"

        with patch(
            "opensignal_its.services.command_service.RUNTIME.get_or_create",
            return_value=("skyline_dms_emulator::dms-1", device),
        ):
            result = asyncio.run(
                CommandService.execute_command_result(
                    device_type="skyline_dms_emulator",
                    config=config,
                    cmd_type="set_message",
                    value={"message": "ROAD WORK AHEAD", "activate_plan": True},
                    safe_command_probe=False,
                    device_id="dms-1",
                )
            )

        self.assertFalse(result.success)
        self.assertEqual("failed", result.lifecycle_stage)
        self.assertTrue(result.acknowledged)
        self.assertEqual(
            "Post-command verification failed: DMS activation state did not match the requested value.",
            result.error,
        )
        self.assertFalse(result.payload["raw_data"]["message_plan_active"])
        self.assertEqual("mismatch", result.payload["extra"]["dms"]["verification_outcome"])

    def test_command_service_reports_failed_dms_lifecycle_when_driver_rejects(self):
        config = DeviceConfig(ip_address="10.0.1.20", name="Skyline DMS")
        device = Device.create("skyline_dms_emulator", config)

        with patch(
            "opensignal_its.services.command_service.RUNTIME.get_or_create",
            return_value=("skyline_dms_emulator::dms-1", device),
        ), patch.object(device, "command", new=AsyncMock(return_value=False)):
            result = asyncio.run(
                CommandService.execute_command_result(
                    device_type="skyline_dms_emulator",
                    config=config,
                    cmd_type="set_message",
                    value={"message": "ROAD WORK AHEAD", "activate_plan": True},
                    safe_command_probe=False,
                    device_id="dms-1",
                )
            )

        self.assertFalse(result.success)
        self.assertEqual("failed", result.lifecycle_stage)
        self.assertEqual("Failed to apply DMS message.", result.error)
        self.assertFalse(result.acknowledged)

    def test_runtime_reuses_same_device_instance(self):
        config = DeviceConfig(ip_address="10.0.0.1", name="Fake")

        first_payload, _ = asyncio.run(
            PollingService.collect_snapshot("fake_registry", config, device_id="dev-1")
        )
        second_payload, _ = asyncio.run(
            PollingService.collect_snapshot("fake_registry", config, device_id="dev-1")
        )

        first_id = first_payload.get("raw_data", {}).get("instance_id")
        second_id = second_payload.get("raw_data", {}).get("instance_id")
        self.assertEqual(first_id, second_id)

    def test_runtime_registry_prunes_stale_entries(self):
        registry = DeviceRuntimeService()
        keep_device = _StopTrackingDevice()
        drop_device = _StopTrackingDevice()
        registry._entries = {
            "siemens_m60::keep": _RuntimeEntry(
                device_type="siemens_m60",
                device_id="keep",
                config=DeviceConfig(ip_address="10.0.0.1", name="Keep"),
                device=keep_device,
            ),
            "siemens_m60::drop": _RuntimeEntry(
                device_type="siemens_m60",
                device_id="drop",
                config=DeviceConfig(ip_address="10.0.0.2", name="Drop"),
                device=drop_device,
            ),
        }

        removed = registry.retain_only({"siemens_m60::keep"})

        self.assertEqual(["siemens_m60::drop"], removed)
        self.assertTrue(drop_device.stopped)
        self.assertFalse(keep_device.stopped)
        self.assertEqual(["siemens_m60::keep"], list(registry._entries.keys()))

    def test_managed_polling_lifecycle(self):
        config = DeviceConfig(ip_address="10.0.0.1", name="Fake")

        async def _scenario() -> tuple[bool, str, dict[str, object], tuple[bool, str]]:
            started, message = await PollingService.start_managed_polling(
                device_type="fake_registry",
                config=config,
                device_id="dev-1",
                interval_seconds=1,
            )
            status = PollingService.runtime_status()
            stopped, stop_message = PollingService.stop_managed_polling(
                device_type="fake_registry",
                config=config,
                device_id="dev-1",
            )
            return started, message, status, (stopped, stop_message)

        started, message, status, stop_result = asyncio.run(_scenario())
        stopped, stop_message = stop_result

        self.assertTrue(started)
        self.assertIn("started", message)
        self.assertEqual(1, status["count"])
        self.assertEqual(1, status["running_count"])
        self.assertTrue(stopped)
        self.assertIn("stopped", stop_message)

    def test_managed_polling_multiple_devices_runtime_counts(self):
        config1 = DeviceConfig(ip_address="10.0.0.1", name="Fake 1")
        config2 = DeviceConfig(ip_address="10.0.0.2", name="Fake 2")

        async def _scenario() -> tuple[dict[str, object], dict[str, object]]:
            await PollingService.start_managed_polling(
                device_type="fake_registry",
                config=config1,
                device_id="dev-1",
                interval_seconds=1,
            )
            await PollingService.start_managed_polling(
                device_type="fake_registry",
                config=config2,
                device_id="dev-2",
                interval_seconds=1,
            )
            started_status = PollingService.runtime_status()
            PollingService.stop_managed_polling("fake_registry", config1, device_id="dev-1")
            PollingService.stop_managed_polling("fake_registry", config2, device_id="dev-2")
            stopped_status = PollingService.runtime_status()
            return started_status, stopped_status

        started_status, stopped_status = asyncio.run(_scenario())
        self.assertEqual(2, started_status["count"])
        self.assertEqual(2, started_status["running_count"])
        self.assertEqual(2, stopped_status["count"])
        self.assertEqual(0, stopped_status["running_count"])

    def test_audit_store_app_setting_round_trip(self):
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "traffic.db"
            store = AuditStore(str(db_path))

            store.set_app_setting("controller_profiles_json", "[{\"device_id\":\"int-1\"}]")

            self.assertEqual(
                "[{\"device_id\":\"int-1\"}]",
                store.get_app_setting("controller_profiles_json"),
            )
            self.assertEqual("fallback", store.get_app_setting("missing_key", "fallback"))


if __name__ == "__main__":
    unittest.main()
