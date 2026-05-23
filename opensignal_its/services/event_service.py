"""Event timeline and alarm extraction from persisted audit/snapshot activity."""

from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime
from typing import Any

from ..db import STORE


def _parse_iso(ts: str) -> datetime:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return datetime.min


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return default


class EventService:
    @staticmethod
    def build_timeline_and_alarms(
        command_limit: int = 200,
        snapshot_limit: int = 200,
    ) -> dict[str, list[str]]:
        activity = STORE.fetch_recent_activity(command_limit=command_limit, snapshot_limit=snapshot_limit)
        commands = list(activity.get("commands", []))
        snapshots = list(activity.get("snapshots", []))

        timeline_items: list[tuple[datetime, str]] = []
        for cmd in commands:
            ts = str(cmd.get("timestamp", ""))
            dt = _parse_iso(ts)
            device_ip = str(cmd.get("device_ip", "unknown"))
            command_type = str(cmd.get("command_type", "unknown"))
            actor = str(cmd.get("actor", "unknown"))
            allowed = bool(cmd.get("allowed", False))
            success = bool(cmd.get("success", False))
            state = "OK" if success else "FAIL"
            policy = "ALLOWED" if allowed else "DENIED"
            error = str(cmd.get("error", "")).strip()
            suffix = f" error={error}" if error else ""
            timeline_items.append(
                (
                    dt,
                    f"[{ts}] CMD {device_ip} {command_type} actor={actor} {policy} {state}{suffix}",
                )
            )

        for snap in snapshots:
            ts = str(snap.get("timestamp", ""))
            dt = _parse_iso(ts)
            device_ip = str(snap.get("device_ip", "unknown"))
            source = str(snap.get("source", "poll"))
            is_online = bool(snap.get("is_online", False))
            status_text = str(snap.get("status_text", ""))
            state = "ONLINE" if is_online else "OFFLINE"
            timeline_items.append(
                (
                    dt,
                    f"[{ts}] SNAP {device_ip} {source} {state} status={status_text}",
                )
            )

        timeline_items.sort(key=lambda item: item[0], reverse=True)
        timeline = [line for _dt, line in timeline_items]

        alarms: list[str] = []
        offline_threshold = _int_env("OPENSIGNAL_ALARM_OFFLINE_SNAPSHOT_STREAK", 3)
        command_fail_threshold = _int_env("OPENSIGNAL_ALARM_COMMAND_FAILURE_STREAK", 3)

        snapshots_by_device: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for snap in snapshots:
            snapshots_by_device[str(snap.get("device_ip", "unknown"))].append(snap)

        commands_by_device: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for cmd in commands:
            commands_by_device[str(cmd.get("device_ip", "unknown"))].append(cmd)

        for device_ip, device_snaps in snapshots_by_device.items():
            recent = device_snaps[:offline_threshold]
            if len(recent) >= offline_threshold and all(not bool(s.get("is_online", False)) for s in recent):
                alarms.append(
                    f"ALARM offline-streak device={device_ip} count={offline_threshold}"
                )

        for device_ip, device_cmds in commands_by_device.items():
            recent = device_cmds[:command_fail_threshold]
            if len(recent) >= command_fail_threshold and all(not bool(c.get("success", False)) for c in recent):
                alarms.append(
                    f"ALARM command-failure-streak device={device_ip} count={command_fail_threshold}"
                )

        return {
            "timeline": timeline,
            "alarms": alarms,
        }
