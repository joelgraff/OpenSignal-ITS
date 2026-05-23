"""Helpers for fleet profile parsing and selected-device routing."""

from __future__ import annotations

import json
from typing import Any

from ..models.device import DeviceConfig


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
