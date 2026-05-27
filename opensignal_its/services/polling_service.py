"""Polling orchestration services."""

from datetime import datetime, timezone

from ..devices.siemens_m60 import SiemensM60
from ..models.device import DeviceConfig, DeviceStatus
from .device_runtime_service import RUNTIME


class PollingService:
    """Collect status snapshots from devices."""

    @staticmethod
    def _stamp_status(status: DeviceStatus) -> DeviceStatus:
        status.timestamp = datetime.now(timezone.utc)
        return status

    @staticmethod
    async def collect_connection_status(
        device_type: str,
        config: DeviceConfig,
        device_id: str = "",
    ) -> tuple[dict, int]:
        _runtime_key, device = RUNTIME.get_or_create(device_type, config, device_id=device_id)
        await device.connect()
        PollingService._stamp_status(device.status)
        mp_model = getattr(device, "_mp_model", 1)
        return device.status.model_dump(mode="json"), mp_model

    @staticmethod
    async def collect_snapshot(
        device_type: str,
        config: DeviceConfig,
        device_id: str = "",
    ) -> tuple[dict, int]:
        _runtime_key, device = RUNTIME.get_or_create(device_type, config, device_id=device_id)
        success = await device.connect()
        if success:
            device.status = PollingService._stamp_status(await device.poll())
        else:
            device.status = PollingService._stamp_status(device.status)
        status_payload = device.status.model_dump(mode="json")
        mp_model = getattr(device, "_mp_model", 1)
        return status_payload, mp_model

    @staticmethod
    def runtime_status() -> dict[str, object]:
        return RUNTIME.status()

    @staticmethod
    def sync_runtime_registry(profiles: list[dict]) -> list[str]:
        allowed_keys: set[str] = set()
        for profile in profiles:
            device_id = str(profile.get("device_id", "")).strip()
            if not device_id:
                continue
            device_type = str(profile.get("device_type", SiemensM60.device_type)).strip().lower()
            if not device_type:
                device_type = SiemensM60.device_type
            allowed_keys.add(f"{device_type}::{device_id}")
        return RUNTIME.retain_only(allowed_keys)

    @staticmethod
    def reset_runtime() -> None:
        RUNTIME.clear()

    @staticmethod
    async def start_managed_polling(
        device_type: str,
        config: DeviceConfig,
        device_id: str = "",
        interval_seconds: int = 5,
    ) -> tuple[bool, str]:
        runtime_key, device = RUNTIME.get_or_create(device_type, config, device_id=device_id)
        if not await device.connect():
            return False, f"Managed polling start failed: connect failed for {runtime_key}."

        task = getattr(device, "_polling_task", None)
        if task is not None and not task.done():
            return True, f"Managed polling already running for {runtime_key}."

        await device.start_polling(interval_seconds=max(1, int(interval_seconds)))
        return True, f"Managed polling started for {runtime_key}."

    @staticmethod
    def stop_managed_polling(
        device_type: str,
        config: DeviceConfig,
        device_id: str = "",
    ) -> tuple[bool, str]:
        runtime_key, device = RUNTIME.get_existing(device_type, config, device_id=device_id)
        if device is None:
            return False, f"Managed polling not running: runtime {runtime_key} not found."

        task = getattr(device, "_polling_task", None)
        if task is None or task.done():
            return False, f"Managed polling not running for {runtime_key}."

        device.stop_polling()
        return True, f"Managed polling stopped for {runtime_key}."

    @staticmethod
    async def collect_siemens_m60_snapshot(config: DeviceConfig) -> tuple[dict, int]:
        # Compatibility wrapper for existing state call sites.
        return await PollingService.collect_snapshot(SiemensM60.device_type, config)
