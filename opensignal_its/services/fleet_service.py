"""Helpers for fleet profile parsing and selected-device routing."""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

from ..models.device import DeviceConfig
from ..models.fleet import (
    FleetDeviceStatus,
    FleetRefreshView,
    FleetSnapshotEntry,
    RuntimeRegistryView,
)


class FleetService:
    DEFAULT_DEVICE_TYPE = "siemens_m60"

    @staticmethod
    def parse_profiles_json(raw_json: str) -> list[dict[str, Any]]:
        raw = raw_json.strip()
        if not raw:
            return []
        payload = json.loads(raw)
        if not isinstance(payload, list):
            raise ValueError("Device profiles JSON must be a list of profile objects.")

        profiles: list[dict[str, Any]] = []
        for idx, item in enumerate(payload, start=1):
            if not isinstance(item, dict):
                raise ValueError(f"Device profile #{idx} must be an object.")
            device_id = str(item.get("device_id", "")).strip()
            ip_address = str(item.get("ip_address", "")).strip()
            if not device_id:
                raise ValueError(f"Device profile #{idx} is missing device_id.")
            if not ip_address:
                raise ValueError(f"Device profile #{idx} is missing ip_address.")
            profiles.append(
                {
                    "device_id": device_id,
                    "device_type": str(item.get("device_type", FleetService.DEFAULT_DEVICE_TYPE)).strip()
                    or FleetService.DEFAULT_DEVICE_TYPE,
                    "ip_address": ip_address,
                    "port": int(item.get("port", 161)),
                    "community": str(item.get("community", "public")),
                    "snmp_version": str(item.get("snmp_version", "auto")),
                    "timeout_seconds": float(item.get("timeout_seconds", 3.0)),
                    "retries": int(item.get("retries", 1)),
                    "name": str(item.get("name", device_id)),
                }
            )
        return profiles

    @staticmethod
    def build_device_config(profile: dict[str, Any]) -> DeviceConfig:
        return DeviceConfig(
            ip_address=str(profile["ip_address"]),
            port=int(profile.get("port", 161)),
            name=str(profile.get("name", profile.get("device_id", "Device"))),
            community=str(profile.get("community", "public")),
            snmp_version=str(profile.get("snmp_version", "auto")),
            timeout_seconds=float(profile.get("timeout_seconds", 3.0)),
            retries=int(profile.get("retries", 1)),
        )

    @staticmethod
    def select_profile(
        profiles: list[dict[str, Any]],
        selected_device_id: str,
    ) -> dict[str, Any] | None:
        if not profiles:
            return None
        target = selected_device_id.strip()
        if target:
            for profile in profiles:
                if str(profile.get("device_id", "")).strip() == target:
                    return profile
        return profiles[0]

    @staticmethod
    def resolve_target(
        profiles: list[dict[str, Any]],
        selected_device_id: str,
        fallback_config: DeviceConfig,
        fallback_device_id: str = "single-device",
        fallback_device_type: str = DEFAULT_DEVICE_TYPE,
    ) -> tuple[str, str, DeviceConfig]:
        selected = FleetService.select_profile(profiles, selected_device_id)
        if selected is None:
            return (
                fallback_device_type,
                fallback_device_id.strip() or "single-device",
                fallback_config,
            )

        config = FleetService.build_device_config(selected)
        return (
            str(selected.get("device_type", FleetService.DEFAULT_DEVICE_TYPE)),
            str(selected.get("device_id", config.name)),
            config,
        )

    @staticmethod
    def summarize_status_map(status_map: dict[str, dict[str, Any]]) -> dict[str, int]:
        total = len(status_map)
        online = sum(1 for payload in status_map.values() if bool(payload.get("is_online", False)))
        offline = max(0, total - online)
        return {
            "total": total,
            "online": online,
            "offline": offline,
        }

    @staticmethod
    def format_status_row(device_id: str, device_type: str, payload: dict[str, Any]) -> str:
        is_online = bool(payload.get("is_online", False))
        status_text = str(payload.get("status_text", "unknown"))
        return f"{device_id} [{device_type}] {'ONLINE' if is_online else 'OFFLINE'} - {status_text}"

    @staticmethod
    def build_snapshot_entry(
        device_id: str,
        device_type: str,
        payload: dict[str, Any] | None,
        mp_model: int,
        error: str = "",
    ) -> FleetSnapshotEntry:
        if error:
            status_payload = FleetDeviceStatus(
                device_type=device_type,
                is_online=False,
                status_text=f"error: {error}",
                timestamp="",
            )
            row = f"{device_id} [{device_type}] ERROR - {error}"
            return FleetSnapshotEntry(
                device_id=device_id,
                device_type=device_type,
                status=status_payload,
                row=row,
                payload=None,
                mp_model=int(mp_model),
            )

        safe_payload = dict(payload or {})
        status_payload = FleetDeviceStatus(
            device_type=device_type,
            is_online=bool(safe_payload.get("is_online", False)),
            status_text=str(safe_payload.get("status_text", "unknown")),
            timestamp=str(safe_payload.get("timestamp", "")),
        )
        return FleetSnapshotEntry(
            device_id=device_id,
            device_type=device_type,
            status=status_payload,
            row=FleetService.format_status_row(device_id, device_type, safe_payload),
            payload=safe_payload,
            mp_model=int(mp_model),
        )

    @staticmethod
    def compile_refresh_view(
        entries: list[FleetSnapshotEntry],
        selected_device_id: str,
    ) -> FleetRefreshView:
        rows: list[str] = []
        status_by_id: dict[str, FleetDeviceStatus] = {}
        selected_payload: dict[str, Any] | None = None
        selected_mp_model = 1
        selected_device_type = FleetService.DEFAULT_DEVICE_TYPE

        for entry in entries:
            device_id = str(entry.device_id)
            rows.append(str(entry.row))
            status_by_id[device_id] = entry.status
            if device_id != selected_device_id:
                continue
            payload = entry.payload
            if isinstance(payload, dict):
                selected_payload = dict(payload)
                selected_mp_model = int(entry.mp_model)
                selected_device_type = str(entry.device_type or FleetService.DEFAULT_DEVICE_TYPE)

        return FleetRefreshView(
            rows=rows,
            status_by_id=status_by_id,
            selected_payload=selected_payload,
            selected_mp_model=selected_mp_model,
            selected_device_type=selected_device_type,
            selected_device_id=selected_device_id,
        )

    @staticmethod
    async def collect_refresh_view(
        profiles: list[dict[str, Any]],
        selected_device_id: str,
        collector: Callable[..., Awaitable[tuple[dict[str, Any], int]]],
    ) -> FleetRefreshView:
        selected = FleetService.select_profile(profiles, selected_device_id)
        effective_selected_id = str(selected.get("device_id", "")).strip() if selected is not None else ""

        entries: list[FleetSnapshotEntry] = []
        for profile in profiles:
            device_id = str(profile.get("device_id", "unknown"))
            device_type = str(profile.get("device_type", FleetService.DEFAULT_DEVICE_TYPE))
            config = FleetService.build_device_config(profile)
            try:
                payload, mp_model = await collector(device_type, config, device_id=device_id)
                entries.append(
                    FleetService.build_snapshot_entry(
                        device_id=device_id,
                        device_type=device_type,
                        payload=payload,
                        mp_model=mp_model,
                    )
                )
            except Exception as exc:
                entries.append(
                    FleetService.build_snapshot_entry(
                        device_id=device_id,
                        device_type=device_type,
                        payload=None,
                        mp_model=1,
                        error=str(exc),
                    )
                )

        view = FleetService.compile_refresh_view(entries, effective_selected_id)
        view.selected_device_id = effective_selected_id
        return view

    @staticmethod
    def build_runtime_registry_view(status: dict[str, Any]) -> RuntimeRegistryView:
        count = int(status.get("count", 0) or 0)
        running_count = int(status.get("running_count", 0) or 0)
        keys = [str(key) for key in status.get("keys", [])]
        running_keys = {str(key) for key in status.get("running_keys", [])}
        rows = [
            f"{key}{' (polling)' if key in running_keys else ''}"
            for key in keys
        ]
        return RuntimeRegistryView(
            summary=f"Runtime registry: {count} devices, {running_count} polling tasks running.",
            rows=rows,
            count=count,
            running_count=running_count,
        )
