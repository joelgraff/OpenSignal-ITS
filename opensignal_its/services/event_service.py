"""Event timeline and alarm extraction from persisted audit/snapshot activity."""

from __future__ import annotations

import os
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from ..db import STORE
from ..models.event import AlarmDisplayRow, AlarmHistoryDisplayRow, EventDisplayView, TimelineDisplayRow


logger = logging.getLogger(__name__)


STORAGE_COUNT_TABLES: tuple[str, ...] = (
    "command_audit",
    "status_snapshots",
    "alarm_acknowledgements",
    "alarm_silences",
    "alarm_events",
    "alert_webhook_queue",
    "alert_webhook_deadletter",
)


def _parse_iso(ts: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def _alarm_field(alarm_key: str, field: str) -> str:
    token = f"{field}="
    for part in alarm_key.split():
        if part.startswith(token):
            return part[len(token):].strip().lower()
    return ""


def _display_label(value: str, default: str) -> str:
    cleaned = value.strip().replace("_", " ").replace("-", " ")
    if not cleaned:
        return default
    return cleaned.title()


def _status_label(value: str) -> str:
    normalized = value.strip().upper()
    if normalized == "OK":
        return "OK"
    return _display_label(value, "Unknown")


def _status_scheme(value: str, fallback: str = "gray") -> str:
    normalized = value.strip().lower()
    if normalized in {"ok", "online"}:
        return "green"
    if normalized in {"fail", "offline", "critical"}:
        return "red"
    if normalized in {"denied", "high", "silenced"}:
        return "orange"
    if normalized in {"warn", "warning", "medium"}:
        return "amber"
    if normalized == "acknowledged":
        return "green"
    return fallback


def _alarm_tokens(alarm_key: str) -> dict[str, str]:
    tokens: dict[str, str] = {}
    for part in alarm_key.split():
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        tokens[key.strip().lower()] = value.strip()
    return tokens


def _split_alarm_metadata(row: str) -> tuple[str, str]:
    base, separator, metadata = row.rpartition(" [")
    if separator and metadata.endswith("]"):
        return base.strip(), metadata[:-1].strip()
    return row.strip(), ""


def _extract_trailing_value(text: str, token: str) -> str:
    _prefix, separator, suffix = text.partition(token)
    if not separator:
        return ""
    return suffix.strip()


def _extract_token_value(text: str, token: str) -> str:
    value = _extract_trailing_value(text, token)
    if not value:
        return ""
    return value.split(" ", 1)[0].strip()


def _extract_between(text: str, start_token: str, end_token: str = "") -> str:
    _prefix, separator, suffix = text.partition(start_token)
    if not separator:
        return ""
    if not end_token:
        return suffix.strip()
    value, _separator, _remainder = suffix.partition(end_token)
    return value.strip()


class EventService:
    @staticmethod
    def storage_table_counts() -> dict[str, int]:
        try:
            return STORE.table_row_counts()
        except Exception as exc:
            logger.warning("Storage table count unavailable: %s", exc)
            return {table: 0 for table in STORAGE_COUNT_TABLES}

    @staticmethod
    def recommended_silence_minutes(alarm_key: str) -> int:
        key = alarm_key.strip()
        default_minutes = _int_env("OPENSIGNAL_ALARM_SILENCE_DEFAULT_MINUTES", 30)
        if not key:
            return default_minutes

        severity = _alarm_field(key, "severity")
        alarm_type = _alarm_field(key, "type")

        if alarm_type == "offline-streak":
            return _int_env("OPENSIGNAL_ALARM_SILENCE_OFFLINE_STREAK_MINUTES", 15)
        if alarm_type == "command-failure-streak":
            return _int_env("OPENSIGNAL_ALARM_SILENCE_COMMAND_FAILURE_STREAK_MINUTES", 20)

        if severity == "critical":
            return _int_env("OPENSIGNAL_ALARM_SILENCE_CRITICAL_MINUTES", 15)
        if severity == "high":
            return _int_env("OPENSIGNAL_ALARM_SILENCE_HIGH_MINUTES", 20)

        return default_minutes

    @staticmethod
    def build_timeline_and_alarms(
        command_limit: int = 200,
        snapshot_limit: int = 200,
        window_minutes: int | None = 60,
    ) -> dict[str, list[str]]:
        activity = STORE.fetch_recent_activity(command_limit=command_limit, snapshot_limit=snapshot_limit)
        commands = list(activity.get("commands", []))
        snapshots = list(activity.get("snapshots", []))

        if window_minutes is not None:
            window_start = datetime.now(timezone.utc) - timedelta(minutes=max(1, window_minutes))
            commands = [
                c for c in commands if _parse_iso(str(c.get("timestamp", ""))) >= window_start
            ]
            snapshots = [
                s for s in snapshots if _parse_iso(str(s.get("timestamp", ""))) >= window_start
            ]

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

        alarm_candidates: list[tuple[int, str]] = []
        offline_threshold = _int_env("OPENSIGNAL_ALARM_OFFLINE_SNAPSHOT_STREAK", 3)
        command_fail_threshold = _int_env("OPENSIGNAL_ALARM_COMMAND_FAILURE_STREAK", 3)

        snapshots_by_device: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for snap in snapshots:
            snapshots_by_device[str(snap.get("device_ip", "unknown"))].append(snap)

        commands_by_device: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for cmd in commands:
            commands_by_device[str(cmd.get("device_ip", "unknown"))].append(cmd)

        for device_ip, device_snaps in snapshots_by_device.items():
            ordered = sorted(
                device_snaps,
                key=lambda row: _parse_iso(str(row.get("timestamp", ""))),
                reverse=True,
            )
            recent = ordered[:offline_threshold]
            if len(recent) >= offline_threshold and all(not bool(s.get("is_online", False)) for s in recent):
                alarm_candidates.append(
                    (
                        2,
                        f"ALARM severity=critical type=offline-streak device={device_ip} threshold={offline_threshold}",
                    )
                )

        for device_ip, device_cmds in commands_by_device.items():
            ordered = sorted(
                device_cmds,
                key=lambda row: _parse_iso(str(row.get("timestamp", ""))),
                reverse=True,
            )
            recent = ordered[:command_fail_threshold]
            if len(recent) >= command_fail_threshold and all(not bool(c.get("success", False)) for c in recent):
                alarm_candidates.append(
                    (
                        1,
                        (
                            "ALARM severity=high type=command-failure-streak "
                            f"device={device_ip} threshold={command_fail_threshold}"
                        ),
                    )
                )

        alarm_candidates.sort(key=lambda item: (-item[0], item[1]))
        alarms = [alarm for _rank, alarm in alarm_candidates]

        acknowledgements = STORE.list_alarm_acknowledgements()
        silences = STORE.list_alarm_silences()
        active_alarms: list[str] = []
        acknowledged_alarms: list[str] = []
        silenced_alarms: list[str] = []
        for alarm in alarms:
            silence = silences.get(alarm)
            if silence is not None:
                silenced_alarms.append(
                    (
                        f"{alarm} [SILENCED by {silence['silenced_by']} "
                        f"until {silence['silenced_until']}]"
                    )
                )
                continue

            ack = acknowledgements.get(alarm)
            if ack is None:
                active_alarms.append(alarm)
            else:
                acknowledged_alarms.append(
                    f"{alarm} [ACK by {ack['acknowledged_by']} at {ack['acknowledged_at']}]"
                )

        return {
            "timeline": timeline,
            "alarms": active_alarms,
            "acknowledged_alarms": acknowledged_alarms,
            "silenced_alarms": silenced_alarms,
        }

    @staticmethod
    def build_display_view(payload: dict[str, list[str]]) -> EventDisplayView:
        return EventDisplayView(
            timeline=[
                EventService._build_timeline_display_row(row)
                for row in payload.get("timeline", [])
            ],
            alarms=[
                EventService._build_alarm_display_row(row, state_label="Active")
                for row in payload.get("alarms", [])
            ],
            acknowledged_alarms=[
                EventService._build_alarm_display_row(row, state_label="Acknowledged")
                for row in payload.get("acknowledged_alarms", [])
            ],
            silenced_alarms=[
                EventService._build_alarm_display_row(row, state_label="Silenced")
                for row in payload.get("silenced_alarms", [])
            ],
        )

    @staticmethod
    def _build_alarm_display_row(row: str, state_label: str) -> AlarmDisplayRow:
        alarm_key, metadata = _split_alarm_metadata(row)
        tokens = _alarm_tokens(alarm_key)
        severity = tokens.get("severity", "unknown")
        alarm_type = tokens.get("type", "unknown")
        threshold = tokens.get("threshold", "")
        detail = f"Threshold {threshold}" if threshold else "Threshold not provided"
        return AlarmDisplayRow(
            alarm_key=alarm_key,
            severity=severity,
            severity_label=_display_label(severity, "Unknown"),
            severity_scheme=_status_scheme(severity),
            alarm_type=alarm_type,
            summary=_display_label(alarm_type, "Alarm"),
            device_ip=tokens.get("device", "unknown"),
            detail=detail,
            state_label=state_label,
            state_scheme=_status_scheme(state_label),
            state_detail=metadata,
            raw=row,
        )

    @staticmethod
    def _build_timeline_display_row(row: str) -> TimelineDisplayRow:
        raw = row.strip()
        timestamp = ""
        remainder = raw
        if raw.startswith("[") and "] " in raw:
            timestamp, remainder = raw[1:].split("] ", 1)
        tokens = remainder.split()
        kind = tokens[0] if tokens else "event"

        if kind == "CMD":
            device_ip = tokens[1] if len(tokens) > 1 else "unknown"
            command_type = tokens[2] if len(tokens) > 2 else "unknown"
            actor = _extract_token_value(remainder, " actor=")
            policy = "DENIED" if " DENIED" in remainder else "ALLOWED" if " ALLOWED" in remainder else "UNKNOWN"
            status = "FAIL" if " FAIL" in remainder else "OK" if " OK" in remainder else "UNKNOWN"
            error = _extract_trailing_value(remainder, " error=")
            detail_parts = []
            if actor:
                detail_parts.append(f"Actor {actor}")
            if policy != "UNKNOWN":
                detail_parts.append(_display_label(policy, "Unknown"))
            if error:
                detail_parts.append(f"Error {error}")
            return TimelineDisplayRow(
                timestamp=timestamp,
                kind="command",
                kind_label="Command",
                kind_scheme="blue",
                device_ip=device_ip,
                summary=_display_label(command_type, "Command"),
                detail=" | ".join(detail_parts) or "No command detail.",
                status_label=_status_label(status),
                status_scheme=_status_scheme(policy if policy == "DENIED" else status),
                raw=row,
            )

        if kind == "SNAP":
            device_ip = tokens[1] if len(tokens) > 1 else "unknown"
            source = tokens[2] if len(tokens) > 2 else "poll"
            status = tokens[3] if len(tokens) > 3 else "unknown"
            status_text = _extract_trailing_value(remainder, " status=")
            detail_parts = []
            if source:
                detail_parts.append(_display_label(source, "Poll"))
            if status_text:
                detail_parts.append(status_text)
            return TimelineDisplayRow(
                timestamp=timestamp,
                kind="snapshot",
                kind_label="Snapshot",
                kind_scheme="gray",
                device_ip=device_ip,
                summary="Status Snapshot",
                detail=" | ".join(detail_parts) or "No snapshot detail.",
                status_label=_status_label(status),
                status_scheme=_status_scheme(status),
                raw=row,
            )

        return TimelineDisplayRow(
            timestamp=timestamp,
            kind=kind.lower(),
            kind_label=_display_label(kind, "Event"),
            kind_scheme="gray",
            device_ip="unknown",
            summary="Event",
            detail=remainder,
            status_label="Unknown",
            status_scheme="gray",
            raw=row,
        )

    @staticmethod
    def acknowledge_alarm(alarm_key: str, actor: str, note: str = "") -> tuple[bool, str]:
        key = alarm_key.strip()
        if not key:
            return False, "Alarm acknowledge failed: alarm key is required."
        STORE.acknowledge_alarm(key, actor, note)
        return True, f"Alarm acknowledged: {key}"

    @staticmethod
    def clear_alarm_acknowledgement(alarm_key: str) -> tuple[bool, str]:
        return EventService.clear_alarm_acknowledgement_with_actor(alarm_key, actor="system")

    @staticmethod
    def clear_alarm_acknowledgement_with_actor(
        alarm_key: str,
        actor: str,
        note: str = "",
    ) -> tuple[bool, str]:
        key = alarm_key.strip()
        if not key:
            return False, "Alarm clear failed: alarm key is required."
        STORE.clear_alarm_acknowledgement_with_actor(key, actor=actor, note=note)
        return True, f"Alarm acknowledgement cleared: {key}"

    @staticmethod
    def silence_alarm(
        alarm_key: str,
        actor: str,
        silence_minutes: int,
        note: str = "",
    ) -> tuple[bool, str]:
        key = alarm_key.strip()
        if not key:
            return False, "Alarm silence failed: alarm key is required."
        try:
            minutes = max(1, int(silence_minutes))
        except ValueError:
            return False, "Alarm silence failed: minutes must be numeric."
        STORE.silence_alarm(key, actor, minutes, note)
        return True, f"Alarm silenced for {minutes} minutes: {key}"

    @staticmethod
    def clear_alarm_silence(alarm_key: str) -> tuple[bool, str]:
        return EventService.clear_alarm_silence_with_actor(alarm_key, actor="system")

    @staticmethod
    def clear_alarm_silence_with_actor(
        alarm_key: str,
        actor: str,
        note: str = "",
    ) -> tuple[bool, str]:
        key = alarm_key.strip()
        if not key:
            return False, "Alarm silence clear failed: alarm key is required."
        STORE.clear_alarm_silence_with_actor(key, actor=actor, note=note)
        return True, f"Alarm silence cleared: {key}"

    @staticmethod
    def list_alarm_history_rows(
        limit: int = 50,
        action_filter: str = "all",
        actor_contains: str = "",
        key_contains: str = "",
    ) -> list[str]:
        events = STORE.list_alarm_events(limit=max(500, limit))
        normalized_action = action_filter.strip().lower()
        actor_fragment = actor_contains.strip().lower()
        key_fragment = key_contains.strip().lower()

        filtered: list[dict[str, str]] = []
        for event in events:
            action = str(event.get("action", "")).lower()
            actor = str(event.get("actor", "")).lower()
            key = str(event.get("alarm_key", "")).lower()

            if normalized_action and normalized_action != "all" and action != normalized_action:
                continue
            if actor_fragment and actor_fragment not in actor:
                continue
            if key_fragment and key_fragment not in key:
                continue
            filtered.append(event)

        filtered = filtered[: max(1, int(limit))]
        rows: list[str] = []
        for event in filtered:
            ts = str(event.get("timestamp", ""))
            action = str(event.get("action", "unknown"))
            actor = str(event.get("actor", "unknown"))
            key = str(event.get("alarm_key", ""))
            note = str(event.get("note", "")).strip()
            suffix = f" note={note}" if note else ""
            rows.append(f"[{ts}] ALARM_EVENT {action} actor={actor} key={key}{suffix}")
        return rows

    @staticmethod
    def build_alarm_history_display_rows(rows: list[str]) -> list[AlarmHistoryDisplayRow]:
        return [EventService._build_alarm_history_display_row(row) for row in rows]

    @staticmethod
    def _build_alarm_history_display_row(row: str) -> AlarmHistoryDisplayRow:
        raw = row.strip()
        timestamp = ""
        remainder = raw
        if raw.startswith("[") and "] " in raw:
            timestamp, remainder = raw[1:].split("] ", 1)

        tokens = remainder.split()
        action = tokens[1] if len(tokens) > 1 else "unknown"
        actor = _extract_between(remainder, " actor=", " key=") or "unknown"
        note = _extract_between(remainder, " note=")
        alarm_key = _extract_between(remainder, " key=", " note=") or _extract_between(
            remainder,
            " key=",
        )
        alarm_tokens = _alarm_tokens(alarm_key)
        severity = alarm_tokens.get("severity", "unknown")
        alarm_type = alarm_tokens.get("type", "unknown")
        threshold = alarm_tokens.get("threshold", "")

        action_label_map = {
            "acknowledge": "Ack",
            "clear_acknowledgement": "Clear Ack",
            "silence": "Silence",
            "clear_silence": "Clear Silence",
        }
        action_scheme_map = {
            "acknowledge": "green",
            "clear_acknowledgement": "gray",
            "silence": "orange",
            "clear_silence": "gray",
        }

        detail_parts = [f"Actor {actor}"]
        if threshold:
            detail_parts.append(f"Threshold {threshold}")

        return AlarmHistoryDisplayRow(
            timestamp=timestamp,
            action=action,
            action_label=action_label_map.get(action, _display_label(action, "Unknown")),
            action_scheme=action_scheme_map.get(action, "gray"),
            actor=actor,
            alarm_key=alarm_key,
            severity=severity,
            severity_label=_display_label(severity, "Unknown"),
            severity_scheme=_status_scheme(severity),
            alarm_type=alarm_type,
            summary=_display_label(alarm_type, "Alarm"),
            device_ip=alarm_tokens.get("device", "unknown"),
            detail=" | ".join(detail_parts),
            note=note,
            raw=row,
        )
