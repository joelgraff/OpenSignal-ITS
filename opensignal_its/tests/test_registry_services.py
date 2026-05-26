import asyncio
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from opensignal_its.devices.base import Device
from opensignal_its.models.device import DeviceConfig, DeviceStatus
from opensignal_its.db.audit_store import AuditStore
from opensignal_its.services.command_service import CommandService
from opensignal_its.services.polling_service import PollingService


class _FakeRegistryDevice(Device):
    device_type = "fake_registry"

    async def connect(self) -> bool:
        self.status.is_online = True
        self.status.status_text = "connected"
        return True

    async def poll(self) -> DeviceStatus:
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
        self.assertEqual(1, mp_model)

    def test_polling_service_collect_connection_status_uses_connect_only(self):
        config = DeviceConfig(ip_address="10.0.0.1", name="Fake")

        payload, mp_model = asyncio.run(
            PollingService.collect_connection_status("fake_registry", config, device_id="dev-1")
        )

        self.assertTrue(payload["is_online"])
        self.assertEqual("connected", payload["status_text"])
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
