"""Polling orchestration services."""

import asyncio
from datetime import datetime, timezone
from threading import Lock

from ..devices.siemens_m60 import SiemensM60
from ..models.device import DeviceConfig, DeviceStatus
from ..polling_telemetry import POLLING_TELEMETRY
from .device_runtime_service import RUNTIME


class PollingService:
    """Collect status snapshots from devices."""

    _inflight_snapshot_lock = Lock()
    _inflight_snapshot_results: dict[str, asyncio.Future[tuple[dict, int]]] = {}

    @staticmethod
    def _stamp_status(status: DeviceStatus) -> DeviceStatus:
        status.timestamp = datetime.now(timezone.utc)
        return status

    @staticmethod
    def poll_telemetry(runtime_key: str | None = None) -> dict[str, object]:
        return POLLING_TELEMETRY.snapshot(runtime_key)

    @staticmethod
    def reset_poll_telemetry() -> None:
        POLLING_TELEMETRY.reset()

    @staticmethod
    def _claim_inflight_snapshot(runtime_key: str) -> tuple[asyncio.Future[tuple[dict, int]], bool]:
        with PollingService._inflight_snapshot_lock:
            existing = PollingService._inflight_snapshot_results.get(runtime_key)
            if existing is not None:
                return existing, False

            future: asyncio.Future[tuple[dict, int]] = asyncio.get_running_loop().create_future()
            PollingService._inflight_snapshot_results[runtime_key] = future
            return future, True

    @staticmethod
    def _release_inflight_snapshot(runtime_key: str, future: asyncio.Future[tuple[dict, int]]) -> None:
        with PollingService._inflight_snapshot_lock:
            existing = PollingService._inflight_snapshot_results.get(runtime_key)
            if existing is future:
                del PollingService._inflight_snapshot_results[runtime_key]

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
        inflight_result, is_owner = PollingService._claim_inflight_snapshot(_runtime_key)

        if not is_owner:
            async with POLLING_TELEMETRY.observe(
                _runtime_key,
                "PollingService.collect_snapshot",
                track_overlap=True,
            ):
                return await asyncio.shield(inflight_result)

        status_payload: dict[str, object]
        mp_model: int
        async with POLLING_TELEMETRY.observe(
            _runtime_key,
            "PollingService.collect_snapshot",
            track_overlap=True,
        ):
            try:
                success = await device.connect()
                if success:
                    device.status = PollingService._stamp_status(await device.poll())
                else:
                    device.status = PollingService._stamp_status(device.status)
                status_payload = device.status.model_dump(mode="json")
                mp_model = getattr(device, "_mp_model", 1)
                if not inflight_result.done():
                    inflight_result.set_result((status_payload, mp_model))
                return status_payload, mp_model
            except asyncio.CancelledError:
                if not inflight_result.done():
                    inflight_result.cancel()
                raise
            except Exception as exc:
                if not inflight_result.done():
                    inflight_result.set_exception(exc)
                raise
            finally:
                PollingService._release_inflight_snapshot(_runtime_key, inflight_result)

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
        with PollingService._inflight_snapshot_lock:
            PollingService._inflight_snapshot_results = {}

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
