"""Helpers for fleet profile parsing and selected-device routing."""

from __future__ import annotations

from datetime import datetime
from ipaddress import ip_address
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
    def _normalize_profile_item(item: dict[str, Any], label: str) -> dict[str, Any]:
        if not isinstance(item, dict):
            raise ValueError(f"{label} must be an object.")

        device_id = str(item.get("device_id", "")).strip()
        ip_address = str(item.get("ip_address", "")).strip()
        if not device_id:
            raise ValueError(f"{label} is missing device_id (controller ID).")
        if not ip_address:
            raise ValueError(f"{label} is missing ip_address.")

        return {
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

    @staticmethod
    def parse_profiles_json(raw_json: str) -> list[dict[str, Any]]:
        raw = raw_json.strip()
        if not raw:
            return []
        payload = json.loads(raw)
        if not isinstance(payload, list):
            raise ValueError("Controller profiles JSON must be a list of profile objects.")

        profiles: list[dict[str, Any]] = []
        for idx, item in enumerate(payload, start=1):
            profiles.append(FleetService._normalize_profile_item(item, f"Controller profile #{idx}"))
        return profiles

    @staticmethod
    def normalize_profile(profile: dict[str, Any]) -> dict[str, Any]:
        return FleetService._normalize_profile_item(profile, "Controller profile")

    @staticmethod
    def build_profile_from_form(
        *,
        device_id: str,
        name: str,
        device_type: str,
        ip_address_text: str,
        port_text: str,
        community: str,
        snmp_version: str,
        timeout_text: str,
        retries_text: str,
    ) -> dict[str, Any]:
        try:
            port = int(port_text)
        except ValueError as exc:
            raise ValueError("Port must be an integer.") from exc
        if port < 1 or port > 65535:
            raise ValueError("Port must be between 1 and 65535.")

        try:
            timeout_seconds = float(timeout_text)
        except ValueError as exc:
            raise ValueError("Timeout must be a number.") from exc
        if timeout_seconds <= 0:
            raise ValueError("Timeout must be greater than 0.")

        try:
            retries = int(retries_text)
        except ValueError as exc:
            raise ValueError("Retries must be an integer.") from exc
        if retries < 0:
            raise ValueError("Retries cannot be negative.")

        raw_ip = ip_address_text.strip()
        try:
            normalized_ip = str(ip_address(raw_ip))
        except ValueError as exc:
            raise ValueError("IP address must be a valid IPv4 or IPv6 literal.") from exc

        return FleetService.normalize_profile(
            {
                "device_id": device_id.strip(),
                "name": name.strip() or device_id.strip(),
                "device_type": device_type.strip() or FleetService.DEFAULT_DEVICE_TYPE,
                "ip_address": normalized_ip,
                "port": port,
                "community": community.strip(),
                "snmp_version": snmp_version.strip(),
                "timeout_seconds": timeout_seconds,
                "retries": retries,
            }
        )

    @staticmethod
    def upsert_profile(
        profiles: list[dict[str, Any]],
        profile: dict[str, Any],
    ) -> list[dict[str, Any]]:
        normalized = FleetService.normalize_profile(profile)
        updated = [dict(existing) for existing in profiles]
        for idx, existing in enumerate(updated):
            if str(existing.get("device_id", "")).strip() == normalized["device_id"]:
                updated[idx] = normalized
                break
        else:
            updated.append(normalized)
        return updated

    @staticmethod
    def remove_profile(
        profiles: list[dict[str, Any]],
        device_id: str,
    ) -> list[dict[str, Any]]:
        target = device_id.strip()
        return [
            dict(profile)
            for profile in profiles
            if str(profile.get("device_id", "")).strip() != target
        ]

    @staticmethod
    def dump_profiles_json(profiles: list[dict[str, Any]]) -> str:
        normalized = [FleetService.normalize_profile(profile) for profile in profiles]
        return json.dumps(normalized, indent=2)

    @staticmethod
    def format_profile_row(profile: dict[str, Any]) -> str:
        normalized = FleetService.normalize_profile(profile)
        name = str(normalized.get("name", normalized["device_id"])).strip()
        name_suffix = "" if name == normalized["device_id"] else f" | {name}"
        return (
            f"{normalized['device_id']} | {normalized['ip_address']}"
            f" | {normalized['device_type']}{name_suffix}"
        )

    @staticmethod
    def build_profile_rows(profiles: list[dict[str, Any]]) -> list[str]:
        return [FleetService.format_profile_row(profile) for profile in profiles]

    @staticmethod
    def build_profile_display_rows(
        profiles: list[dict[str, Any]],
        status_map: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for profile in profiles:
            normalized = FleetService.normalize_profile(profile)
            device_id = normalized["device_id"]
            status_payload = dict(status_map.get(device_id, {}))
            if "is_online" not in status_payload:
                status_label = "Unknown"
                status_scheme = "gray"
            elif bool(status_payload.get("is_online", False)):
                status_label = "Online"
                status_scheme = "green"
            else:
                status_label = "Offline"
                status_scheme = "red"

            rows.append(
                {
                    "device_id": device_id,
                    "label": FleetService.format_profile_row(normalized),
                    "status_label": status_label,
                    "status_scheme": status_scheme,
                    "detail_text": str(
                        status_payload.get(
                            "status_text",
                            "No poll data yet." if status_label == "Unknown" else "No status detail.",
                        )
                    ),
                    "updated_text": FleetService.format_status_timestamp(
                        str(status_payload.get("timestamp", ""))
                    ),
                }
            )
        return rows

    @staticmethod
    def format_status_timestamp(timestamp: str) -> str:
        raw = timestamp.strip()
        if not raw:
            return ""
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return f"Updated {parsed.isoformat(timespec='seconds').replace('T', ' ')}"
        except ValueError:
            return f"Updated {raw}"

    @staticmethod
    def filter_profiles(
        profiles: list[dict[str, Any]],
        query: str,
    ) -> list[dict[str, Any]]:
        normalized_query = query.strip().lower()
        if not normalized_query:
            return [dict(profile) for profile in profiles]

        filtered: list[dict[str, Any]] = []
        for profile in profiles:
            normalized = FleetService.normalize_profile(profile)
            haystack = " ".join(
                [
                    normalized["device_id"],
                    normalized["ip_address"],
                    normalized["device_type"],
                    str(normalized.get("name", "")),
                ]
            ).lower()
            if normalized_query in haystack:
                filtered.append(normalized)
        return filtered

    @staticmethod
    def sort_profiles(
        profiles: list[dict[str, Any]],
        sort_key: str,
        descending: bool = False,
    ) -> list[dict[str, Any]]:
        normalized_profiles = [FleetService.normalize_profile(profile) for profile in profiles]
        normalized_key = sort_key.strip().lower()

        def _sort_value(profile: dict[str, Any]):
            if normalized_key == "name":
                return str(profile.get("name", "")).strip().lower(), profile["device_id"].lower()
            if normalized_key == "ip_address":
                return ip_address(str(profile["ip_address"])), profile["device_id"].lower()
            if normalized_key == "device_type":
                return str(profile.get("device_type", "")).strip().lower(), profile["device_id"].lower()
            return profile["device_id"].lower(), str(profile.get("name", "")).strip().lower()

        return sorted(normalized_profiles, key=_sort_value, reverse=descending)

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
            summary=f"Active poll sessions: {count} sites, {running_count} polling loops running.",
            rows=rows,
            count=count,
            running_count=running_count,
        )
