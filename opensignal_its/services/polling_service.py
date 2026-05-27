"""Polling orchestration services."""

import asyncio
import time
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock

from ..devices.siemens_m60 import SiemensM60
from ..models.device import DeviceConfig, DeviceStatus
from ..polling_telemetry import POLLING_TELEMETRY
from .device_runtime_service import RUNTIME


@dataclass
class _SnapshotBackoffState:
    failure_streak: int = 0
    backoff_until: float = 0.0
    last_result: tuple[dict, int] | None = None


class PollingService:
    """Collect status snapshots from devices."""

    _inflight_snapshot_lock = Lock()
    _inflight_snapshot_results: dict[str, asyncio.Future[tuple[dict, int]]] = {}
    _snapshot_backoff_state: dict[str, _SnapshotBackoffState] = {}
    _backoff_failure_threshold = 3
    _backoff_initial_seconds = 15.0
    _backoff_max_seconds = 60.0

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
    def _now_seconds() -> float:
        return time.monotonic()

    @staticmethod
    def _get_backoff_state(runtime_key: str) -> _SnapshotBackoffState:
        state = PollingService._snapshot_backoff_state.get(runtime_key)
        if state is None:
            state = _SnapshotBackoffState()
            PollingService._snapshot_backoff_state[runtime_key] = state
        return state

    @staticmethod
    def _backoff_seconds(failure_streak: int) -> float:
        if failure_streak < PollingService._backoff_failure_threshold:
            return 0.0

        extra_failures = max(0, failure_streak - PollingService._backoff_failure_threshold)
        duration = PollingService._backoff_initial_seconds * (2 ** extra_failures)
        return min(PollingService._backoff_max_seconds, duration)

    @staticmethod
    def _decorate_backoff_payload(
        payload: dict[str, object],
        state: _SnapshotBackoffState,
        now_seconds: float,
        *,
        skipped: bool,
    ) -> dict[str, object]:
        decorated = deepcopy(payload)
        extra = dict(decorated.get("extra", {}))
        extra["poll_backoff"] = {
            "active": True,
            "skipped": skipped,
            "failure_streak": state.failure_streak,
            "next_retry_at": state.backoff_until,
            "stale": skipped,
            "last_known": state.last_result is not None,
            "now": now_seconds,
        }
        decorated["extra"] = extra
        return decorated

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
    def _claim_snapshot_slot(
        runtime_key: str,
        now_seconds: float,
    ) -> tuple[asyncio.Future[tuple[dict, int]] | None, tuple[dict, int] | None, bool]:
        with PollingService._inflight_snapshot_lock:
            inflight = PollingService._inflight_snapshot_results.get(runtime_key)
            if inflight is not None:
                return inflight, None, False

            state = PollingService._snapshot_backoff_state.get(runtime_key)
            if (
                state is not None
                and state.last_result is not None
                and state.backoff_until > now_seconds
            ):
                payload, mp_model = state.last_result
                return None, (
                    PollingService._decorate_backoff_payload(
                        payload,
                        state,
                        now_seconds,
                        skipped=True,
                    ),
                    mp_model,
                ), False

            future: asyncio.Future[tuple[dict, int]] = asyncio.get_running_loop().create_future()
            PollingService._inflight_snapshot_results[runtime_key] = future
            return future, None, True

    @staticmethod
    def _release_inflight_snapshot(runtime_key: str, future: asyncio.Future[tuple[dict, int]]) -> None:
        with PollingService._inflight_snapshot_lock:
            existing = PollingService._inflight_snapshot_results.get(runtime_key)
            if existing is future:
                del PollingService._inflight_snapshot_results[runtime_key]

    @staticmethod
    def _record_snapshot_outcome(
        runtime_key: str,
        payload: dict[str, object],
        mp_model: int,
        now_seconds: float,
        *,
        healthy: bool,
    ) -> dict[str, object]:
        with PollingService._inflight_snapshot_lock:
            state = PollingService._get_backoff_state(runtime_key)
            state.last_result = (deepcopy(payload), mp_model)
            if healthy:
                state.failure_streak = 0
                state.backoff_until = 0.0
                return payload

            state.failure_streak += 1
            backoff_seconds = PollingService._backoff_seconds(state.failure_streak)
            state.backoff_until = now_seconds + backoff_seconds if backoff_seconds > 0 else 0.0
            if state.backoff_until > now_seconds:
                return PollingService._decorate_backoff_payload(
                    payload,
                    state,
                    now_seconds,
                    skipped=False,
                )
            return payload

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
        now_seconds = PollingService._now_seconds()
        inflight_result, backoff_result, is_owner = PollingService._claim_snapshot_slot(
            _runtime_key,
            now_seconds,
        )

        if backoff_result is not None:
            async with POLLING_TELEMETRY.observe(
                _runtime_key,
                "PollingService.collect_snapshot",
                track_overlap=True,
            ):
                return backoff_result

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
                status_payload = PollingService._record_snapshot_outcome(
                    _runtime_key,
                    status_payload,
                    mp_model,
                    now_seconds,
                    healthy=bool(device.status.is_online and not device.status.errors),
                )
                if not inflight_result.done():
                    inflight_result.set_result((status_payload, mp_model))
                return status_payload, mp_model
            except asyncio.CancelledError:
                if not inflight_result.done():
                    inflight_result.cancel()
                raise
            except Exception as exc:
                status_payload = device.status.model_dump(mode="json")
                mp_model = getattr(device, "_mp_model", 1)
                PollingService._record_snapshot_outcome(
                    _runtime_key,
                    status_payload,
                    mp_model,
                    now_seconds,
                    healthy=False,
                )
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
            PollingService._snapshot_backoff_state = {}

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
