"""Long-lived device runtime registry for polling and command reuse."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..devices.base import Device
from ..models.device import DeviceConfig


@dataclass
class _RuntimeEntry:
    device_type: str
    device_id: str
    config: DeviceConfig
    device: Device


class DeviceRuntimeService:
    """Registry of long-lived device instances keyed by device id/type."""

    def __init__(self):
        self._entries: dict[str, _RuntimeEntry] = {}

    @staticmethod
    def _runtime_key(device_type: str, device_id: str, config: DeviceConfig) -> str:
        key_id = device_id.strip() or config.ip_address.strip() or config.name.strip() or "device"
        return f"{device_type.strip().lower()}::{key_id}"

    @staticmethod
    def _is_device_polling(device: Device) -> bool:
        task = getattr(device, "_polling_task", None)
        return bool(task is not None and not task.done())

    def runtime_key(self, device_type: str, config: DeviceConfig, device_id: str = "") -> str:
        return self._runtime_key(device_type, device_id, config)

    def get_or_create(self, device_type: str, config: DeviceConfig, device_id: str = "") -> tuple[str, Device]:
        runtime_key = self._runtime_key(device_type, device_id, config)
        existing = self._entries.get(runtime_key)
        if existing is not None:
            setattr(existing.device, "_runtime_key", runtime_key)
            return runtime_key, existing.device

        device = Device.create(device_type, config)
        setattr(device, "_runtime_key", runtime_key)
        self._entries[runtime_key] = _RuntimeEntry(
            device_type=device_type,
            device_id=device_id,
            config=config,
            device=device,
        )
        return runtime_key, device

    def get(self, runtime_key: str) -> Device | None:
        entry = self._entries.get(runtime_key)
        return entry.device if entry is not None else None

    def get_existing(self, device_type: str, config: DeviceConfig, device_id: str = "") -> tuple[str, Device | None]:
        runtime_key = self._runtime_key(device_type, device_id, config)
        entry = self._entries.get(runtime_key)
        if entry is not None:
            setattr(entry.device, "_runtime_key", runtime_key)
        return runtime_key, (entry.device if entry is not None else None)

    def status(self) -> dict[str, Any]:
        running_keys = sorted(
            key
            for key, entry in self._entries.items()
            if self._is_device_polling(entry.device)
        )
        return {
            "count": len(self._entries),
            "keys": sorted(self._entries.keys()),
            "running_count": len(running_keys),
            "running_keys": running_keys,
        }

    def retain_only(self, allowed_keys: set[str]) -> list[str]:
        removed_keys: list[str] = []
        for runtime_key, entry in list(self._entries.items()):
            if runtime_key in allowed_keys:
                continue
            try:
                entry.device.stop_polling()
            except Exception:
                pass
            removed_keys.append(runtime_key)
            del self._entries[runtime_key]
        return removed_keys

    def clear(self):
        for entry in self._entries.values():
            try:
                entry.device.stop_polling()
            except Exception:
                pass
        self._entries = {}


RUNTIME = DeviceRuntimeService()
