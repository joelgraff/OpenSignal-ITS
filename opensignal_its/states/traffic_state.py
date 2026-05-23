import asyncio
import json
import os
import random
from datetime import datetime
from typing import Any
from uuid import uuid4

import reflex as rx

from ..db import CommandAuditRecord, STORE
from ..models.device import DeviceConfig
from ..services import (
    CommandSafetyService,
    CommandService,
    MaintenanceService,
    OperatorAuthService,
    PollingService,
    scheduler_status,
)


class TrafficState(rx.State):
    """Main app state."""

    m60_status: dict = {}
    m60_status_json: str = ""
    status_text: str = "No status yet"
    active_snmp_version: str = "unknown"
    current_pattern: str = "Unknown"
    unit_status: str = "unknown"
    green_phases: str = "none"
    yellow_phases: str = "none"
    red_phases: str = "none"
    vehicle_calls: str = "none"
    ped_calls: str = "none"
    remaining_time_summary: str = "none"
    timer_mode_text: str = "unknown"
    ring_status_summary: str = "unknown"
    ring_status_lines: list[str] = []
    ring_status_console_text: str = "RING STATUS CONSOLE\n(no data)"
    last_ring_status_raw: dict[str, int] = {}
    ring_state_age_seconds: dict[str, int] = {}
    phase_data: dict[str, dict[str, bool | int]] = {}
    phase_current_pattern: str = "Unknown"
    phase_unit_control_status: str = "unknown"
    phase_detail_lines: list[str] = []
    last_timer_snapshot: dict[str, int] = {}
    phase_state_age_seconds: dict[str, int] = {}
    last_phase_state_signature: dict[str, str] = {}
    is_online: bool = False
    last_updated: str = ""
    error: str = ""
    is_loading: bool = False
    ip_address: str = "166.156.88.223"
    port_text: str = "161"
    community: str = "public"
    snmp_version: str = "auto"
    timeout_text: str = "3"
    retries_text: str = "1"
    login_username_input: str = ""
    login_password_input: str = ""
    is_authenticated: bool = False
    current_operator: str = ""
    auth_notice: str = "Operator not authenticated."
    failed_login_attempts: int = 0
    login_lockout_until: str = ""
    safe_command_probe: bool = True
    operator_key_input: str = ""
    write_unlock_seconds_text: str = "120"
    write_unlock_until: str = ""
    write_mode_active: bool = False
    safety_notice: str = "Write mode locked."
    confirmation_input: str = ""
    pending_confirmation_token: str = ""
    pending_confirmation_expires: str = ""
    pending_command_type: str = ""
    pending_command_value_json: str = ""
    pending_confirmation_notice: str = ""
    maintenance_notice: str = ""
    runtime_health_notice: str = "Runtime health not refreshed yet."
    retention_scheduler_enabled: bool = False
    retention_scheduler_running: bool = False
    retention_scheduler_interval_text: str = "unknown"
    retention_scheduler_error: str = ""
    last_retention_cleanup_at: str = ""
    last_retention_cleanup_result: str = "No retention cleanup run yet."
    auto_refresh_enabled: bool = True
    refresh_interval_text: str = "5"
    auto_reconnect_enabled: bool = True
    reconnect_interval_text: str = "10"
    auto_refresh_running: bool = False

    def update_ip_address(self, value: str):
        self.ip_address = value

    def update_port_text(self, value: str):
        self.port_text = value

    def update_community(self, value: str):
        self.community = value

    def update_snmp_version(self, value: str):
        self.snmp_version = value

    def update_timeout_text(self, value: str):
        self.timeout_text = value

    def update_retries_text(self, value: str):
        self.retries_text = value

    def update_safe_command_probe(self, value: bool):
        self.safe_command_probe = value
        if value:
            self.write_mode_active = False
            self.write_unlock_until = ""
            self.safety_notice = "Probe mode enabled. Write mode locked."

    def update_operator_key_input(self, value: str):
        self.operator_key_input = value

    def update_login_username_input(self, value: str):
        self.login_username_input = value

    def update_login_password_input(self, value: str):
        self.login_password_input = value

    def update_write_unlock_seconds_text(self, value: str):
        self.write_unlock_seconds_text = value

    def update_confirmation_input(self, value: str):
        self.confirmation_input = value

    def update_auto_refresh_enabled(self, value: bool):
        self.auto_refresh_enabled = value

    def update_refresh_interval_text(self, value: str):
        self.refresh_interval_text = value

    def update_auto_reconnect_enabled(self, value: bool):
        self.auto_reconnect_enabled = value

    def update_reconnect_interval_text(self, value: str):
        self.reconnect_interval_text = value

    def _refresh_interval_seconds(self) -> float:
        try:
            return max(1.0, float(self.refresh_interval_text))
        except ValueError:
            return 5.0

    def _reconnect_interval_seconds(self) -> float:
        try:
            return max(2.0, float(self.reconnect_interval_text))
        except ValueError:
            return 10.0

    def _write_unlock_seconds(self) -> int:
        try:
            return max(15, int(self.write_unlock_seconds_text))
        except ValueError:
            return 120

    @staticmethod
    def _max_login_attempts() -> int:
        try:
            return max(1, int(os.getenv("OPENSIGNAL_MAX_LOGIN_ATTEMPTS", "5")))
        except ValueError:
            return 5

    @staticmethod
    def _login_lockout_seconds() -> int:
        try:
            return max(10, int(os.getenv("OPENSIGNAL_LOGIN_LOCKOUT_SECONDS", "300")))
        except ValueError:
            return 300

    def _actor_name(self) -> str:
        return self.current_operator if self.current_operator else "anonymous"

    def _is_login_locked(self) -> bool:
        if not self.login_lockout_until:
            return False
        return not self._has_expired(self.login_lockout_until)

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.utcnow().isoformat()

    def _has_expired(self, ts: str) -> bool:
        parsed = self._parse_timestamp(ts)
        now = datetime.utcnow()
        if parsed is None:
            return True
        # _parse_timestamp may return timezone-aware dt if offset is included.
        if parsed.tzinfo is not None:
            return now.replace(tzinfo=parsed.tzinfo) >= parsed
        return now >= parsed

    def _requires_confirmation(self, cmd_type: str) -> bool:
        if self.safe_command_probe:
            return False
        return cmd_type in {
            "select_pattern",
            "set_mode",
            "manual_hold",
            "advance_phase",
        }

    def _start_command_confirmation(self, cmd_type: str, value: Any):
        token = str(random.randint(100000, 999999))
        expires = datetime.utcnow().timestamp() + 90
        self.pending_confirmation_token = token
        self.pending_confirmation_expires = datetime.utcfromtimestamp(expires).isoformat()
        self.pending_command_type = cmd_type
        self.pending_command_value_json = json.dumps(value)
        self.pending_confirmation_notice = (
            f"Confirmation required for {cmd_type}. Enter token {token} within 90 seconds."
        )

    def _build_config(self) -> DeviceConfig:
        port = int(self.port_text)
        timeout_seconds = float(self.timeout_text)
        retries = int(self.retries_text)
        return DeviceConfig(
            ip_address=self.ip_address.strip(),
            port=port,
            name="Siemens M60 Test",
            community=self.community.strip(),
            snmp_version=self.snmp_version.strip().lower(),
            timeout_seconds=timeout_seconds,
            retries=retries,
        )

    def _parse_timestamp(self, ts: str) -> datetime | None:
        if not ts:
            return None
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _poll_delta_seconds(self, previous_ts: str, current_ts: str) -> int:
        prev = self._parse_timestamp(previous_ts)
        curr = self._parse_timestamp(current_ts)
        if prev is None or curr is None:
            return 0
        delta = int((curr - prev).total_seconds())
        return max(0, delta)

    def _apply_phase_payload(self, payload: dict, poll_delta_seconds: int = 0):
        raw_data = payload.get("raw_data", {}) if isinstance(payload, dict) else {}
        extra = payload.get("extra", {}) if isinstance(payload, dict) else {}

        self.current_pattern = str(raw_data.get("current_pattern", "Unknown"))
        self.unit_status = str(raw_data.get("unit_status", "unknown"))

        summary = extra.get("phase_summary", {}) if isinstance(extra, dict) else {}
        greens = summary.get("green", []) if isinstance(summary, dict) else []
        yellows = summary.get("yellow", []) if isinstance(summary, dict) else []
        reds = summary.get("red", []) if isinstance(summary, dict) else []
        veh_calls = summary.get("vehicle_calls", []) if isinstance(summary, dict) else []
        ped_calls = summary.get("ped_calls", []) if isinstance(summary, dict) else []

        self.green_phases = ", ".join(str(v) for v in greens) if greens else "none"
        self.yellow_phases = ", ".join(str(v) for v in yellows) if yellows else "none"
        self.red_phases = ", ".join(str(v) for v in reds) if reds else "none"
        self.vehicle_calls = ", ".join(str(v) for v in veh_calls) if veh_calls else "none"
        self.ped_calls = ", ".join(str(v) for v in ped_calls) if ped_calls else "none"

        phases = extra.get("phases", {}) if isinstance(extra, dict) else {}
        lines: list[str] = []
        timer_parts: list[str] = []
        estimated_countdown_parts: list[str] = []
        timer_snapshot: dict[str, int] = {}
        next_phase_state_age: dict[str, int] = dict(self.phase_state_age_seconds)
        next_phase_signatures: dict[str, str] = dict(self.last_phase_state_signature)
        phase_data: dict[str, dict[str, bool | int]] = {}
        self.phase_current_pattern = self.current_pattern
        self.phase_unit_control_status = self.unit_status
        if isinstance(phases, dict):
            for phase in range(1, 17):
                phase_key = str(phase)
                entry = phases.get(phase_key, {})
                if not isinstance(entry, dict):
                    entry = {}
                flags = []
                if entry.get("green"):
                    flags.append("G")
                if entry.get("yellow"):
                    flags.append("Y")
                if entry.get("red"):
                    flags.append("R")
                state = "/".join(flags) if flags else "OFF"
                v_call = "Y" if entry.get("vehicle_call") else "N"
                p_call = "Y" if entry.get("ped_call") else "N"
                timer = int(entry.get("time_remaining", 0) or 0)
                max_green_1 = int(entry.get("max_green_1", 0) or 0)

                signature = f"G{1 if entry.get('green') else 0}Y{1 if entry.get('yellow') else 0}R{1 if entry.get('red') else 0}"
                previous_signature = self.last_phase_state_signature.get(phase_key, "")
                if signature == previous_signature and poll_delta_seconds > 0:
                    next_phase_state_age[phase_key] = next_phase_state_age.get(phase_key, 0) + poll_delta_seconds
                else:
                    next_phase_state_age[phase_key] = 0
                next_phase_signatures[phase_key] = signature
                state_age = next_phase_state_age.get(phase_key, 0)

                estimated_countdown = -1
                if bool(entry.get("green")) and max_green_1 > 0:
                    estimated_countdown = max(0, max_green_1 - state_age)

                timer_snapshot[phase_key] = timer
                if estimated_countdown >= 0:
                    lines.append(
                        f"P{phase:02d} {state:6s} V:{v_call} P:{p_call} T:{timer:>3d}s Est:{estimated_countdown:>3d}s Max1:{max_green_1:>3d}s"
                    )
                    estimated_countdown_parts.append(f"P{phase}:{estimated_countdown}")
                else:
                    lines.append(f"P{phase:02d} {state:6s} V:{v_call} P:{p_call} T:{timer:>3d}s")
                phase_data[f"Phase_{phase}"] = {
                    "green": bool(entry.get("green")),
                    "yellow": bool(entry.get("yellow")),
                    "red": bool(entry.get("red")),
                    "has_call": bool(entry.get("vehicle_call") or entry.get("ped_call")),
                    "vehicle_call": bool(entry.get("vehicle_call")),
                    "ped_call": bool(entry.get("ped_call")),
                    "time_remaining": timer,
                }
                if timer > 0:
                    timer_parts.append(f"P{phase}:{timer}")
        self.phase_detail_lines = lines
        self.phase_data = phase_data
        self.phase_state_age_seconds = next_phase_state_age
        self.last_phase_state_signature = next_phase_signatures

        def _phase_char(phase: int, mode: str) -> str:
            entry = phase_data.get(f"Phase_{phase}", {})
            if not isinstance(entry, dict):
                entry = {}
            is_green = bool(entry.get("green", False))
            is_yellow = bool(entry.get("yellow", False))
            has_veh = bool(entry.get("vehicle_call", False))
            has_ped = bool(entry.get("ped_call", False))
            if mode == "on":
                # Manual O/N row: O is live active; next-phase (N) is not exposed by current OIDs.
                return "O" if (is_green or is_yellow) else "."
            if mode == "veh":
                return "C" if has_veh else "."
            if mode == "ped":
                return "C" if has_ped else "."
            return "."

        def _phase_cells(mode: str) -> tuple[str, str]:
            left = "".join(_phase_char(p, mode) for p in range(1, 9))
            right = "".join(_phase_char(p, mode) for p in range(9, 17))
            return left, right

        def _ring_state_abbrev(state_name: str) -> str:
            mapping = {
                "Min Green": "MGRN",
                "Extension": "PASS",
                "Maximum": "MAX1",
                "Green Rest": "GRN RST",
                "Yellow Change": "YEL",
                "Red Clearance": "RED",
                "Red Rest": "RED RST",
            }
            return mapping.get(state_name, state_name.upper())

        def _active_ring_timer(start_phase: int, end_phase: int) -> int:
            # Use live per-phase timer from the first active interval in the ring bank.
            for p in range(start_phase, end_phase + 1):
                entry = phase_data.get(f"Phase_{p}", {})
                if not isinstance(entry, dict):
                    continue
                if bool(entry.get("green", False)) or bool(entry.get("yellow", False)):
                    return int(entry.get("time_remaining", 0) or 0)
            return 0

        if estimated_countdown_parts:
            self.remaining_time_summary = ", ".join(estimated_countdown_parts)
            self.timer_mode_text = "estimated countdown (max green)"
        else:
            self.remaining_time_summary = ", ".join(timer_parts) if timer_parts else "none"
            if self.last_timer_snapshot:
                self.timer_mode_text = "dynamic" if self.last_timer_snapshot != timer_snapshot else "static"
            else:
                self.timer_mode_text = "unknown"

        ring_status = extra.get("ring_status", {}) if isinstance(extra, dict) else {}
        ring_lines: list[str] = []
        ring_parts: list[str] = []
        next_ring_raw: dict[str, int] = {}
        next_ring_age: dict[str, int] = dict(self.ring_state_age_seconds)
        if isinstance(ring_status, dict):
            for ring in (1, 2):
                ring_entry = ring_status.get(str(ring), {})
                if not isinstance(ring_entry, dict):
                    ring_entry = {}
                state_name = str(ring_entry.get("state_name", "Unavailable"))
                state_code = int(ring_entry.get("state_code", -1) or -1)
                bit_a = "1" if bool(ring_entry.get("bit_a", False)) else "0"
                bit_b = "1" if bool(ring_entry.get("bit_b", False)) else "0"
                bit_c = "1" if bool(ring_entry.get("bit_c", False)) else "0"
                raw = ring_entry.get("raw")
                raw_int = int(raw) if isinstance(raw, int) else -1
                next_ring_raw[str(ring)] = raw_int
                prev_raw = self.last_ring_status_raw.get(str(ring), -2)
                if raw_int == prev_raw and poll_delta_seconds > 0:
                    next_ring_age[str(ring)] = next_ring_age.get(str(ring), 0) + poll_delta_seconds
                else:
                    next_ring_age[str(ring)] = 0
                gap_out = bool(ring_entry.get("gap_out", False))
                max_out = bool(ring_entry.get("max_out", False))
                force_off = bool(ring_entry.get("force_off", False))
                age = next_ring_age.get(str(ring), 0)
                ring_parts.append(f"R{ring}:{state_name} ({age}s)")
                ring_lines.append(
                    f"R{ring}  raw={raw_int:>3d}  code={state_code:>2d}  bits={bit_a}{bit_b}{bit_c}  state={state_name:<14}  age={age:>3d}s  gap={'Y' if gap_out else 'N'} max={'Y' if max_out else 'N'} force={'Y' if force_off else 'N'}"
                )
        self.last_ring_status_raw = next_ring_raw
        self.ring_state_age_seconds = next_ring_age
        self.ring_status_summary = ", ".join(ring_parts) if ring_parts else "unknown"
        self.ring_status_lines = ring_lines

        # Approximate ring max timers from first active green phase in each half-bank.
        ring1_max1 = 0
        ring2_max1 = 0
        for p in range(1, 9):
            entry = phases.get(str(p), {}) if isinstance(phases, dict) else {}
            if bool(entry.get("green", False)) and ring1_max1 == 0:
                ring1_max1 = int(entry.get("max_green_1", 0) or 0)
        for p in range(9, 17):
            entry = phases.get(str(p), {}) if isinstance(phases, dict) else {}
            if bool(entry.get("green", False)) and ring2_max1 == 0:
                ring2_max1 = int(entry.get("max_green_1", 0) or 0)

        r1_age = next_ring_age.get("1", 0)
        r2_age = next_ring_age.get("2", 0)
        r1_state = "UNAVAIL"
        r2_state = "UNAVAIL"
        if isinstance(ring_status, dict):
            r1_state = str((ring_status.get("1") or {}).get("state_name", "UNAVAIL"))
            r2_state = str((ring_status.get("2") or {}).get("state_name", "UNAVAIL"))

        r1 = ring_status.get("1", {}) if isinstance(ring_status, dict) else {}
        r2 = ring_status.get("2", {}) if isinstance(ring_status, dict) else {}
        r1_gap = "Y" if bool((r1 or {}).get("gap_out", False)) else "N"
        r1_max = "Y" if bool((r1 or {}).get("max_out", False)) else "N"
        r1_force = "Y" if bool((r1 or {}).get("force_off", False)) else "N"
        r2_gap = "Y" if bool((r2 or {}).get("gap_out", False)) else "N"
        r2_max = "Y" if bool((r2 or {}).get("max_out", False)) else "N"
        r2_force = "Y" if bool((r2 or {}).get("force_off", False)) else "N"

        on_left, on_right = _phase_cells("on")
        veh_left, veh_right = _phase_cells("veh")
        ped_left, ped_right = _phase_cells("ped")

        r1_interval = _ring_state_abbrev(r1_state)
        r2_interval = _ring_state_abbrev(r2_state)
        r1_timer = _active_ring_timer(1, 8)
        r2_timer = _active_ring_timer(9, 16)

        def _ring_row(label: str, left: str, right: str) -> str:
            return f"{label:<8}{left:<14}{right:<14}"

        def _phase_row(label: str, left: str, right: str) -> str:
            return f"{label:<6}{left:<9}{right:<9}"

        m60_header = [
            "UP/DOWN TO SCROLL                      E-EDIT [1]",
            "RING TIMERS SEQ:00 B:1:1:1:1 CHG PENDING",
            "RING 1           RING 2",
            _ring_row("STATE", f"{r1_interval} {r1_timer:>2}", f"{r2_interval} {r2_timer:>2}"),
            _ring_row("MAX1", f"{ring1_max1:>2}", f"{ring2_max1:>2}"),
            _ring_row("GAP OUT", r1_gap, r2_gap),
            _ring_row("MAX OUT", r1_max, r2_max),
            _ring_row("FORCE", r1_force, r2_force),
            _ring_row("AGE", f"{r1_age:>3}s", f"{r2_age:>3}s"),
            "",
            "PHS..12345678 90123456",
            _phase_row("O/N", on_left, on_right),
            _phase_row("VEH", veh_left, veh_right),
            _phase_row("PED", ped_left, ped_right),
            "",
            "Legend: O=On C=Call .=Inactive",
            "A-UP  B-DN  C-LT  D-RT  E-ENTER  F-PRIOR MENU",
            "",
            "RING DETAIL",
        ]

        if ring_lines:
            code_legend = [
                "0=Min Green  1=Extension  2=Maximum  3=Green Rest",
                "4=Yellow Chg 5=Red Clear  6=Red Rest 7=Undefined",
            ]
            self.ring_status_console_text = "\n".join([
                *m60_header,
                "Ring raw code bits state            age gap max force",
                *ring_lines,
                "",
                *code_legend,
            ])
        else:
            self.ring_status_console_text = "\n".join([
                *m60_header,
                "(no data)",
            ])

        self.last_timer_snapshot = timer_snapshot

    async def _collect_status_snapshot(self) -> tuple[dict, int]:
        """Fetch one controller status snapshot without mutating UI state."""
        config = self._build_config()
        return await PollingService.collect_siemens_m60_snapshot(config)

    def _apply_status_snapshot(self, status_payload: dict, mp_model: int):
        """Apply one status snapshot to state fields used by the UI."""
        previous_updated = self.last_updated
        self.m60_status = status_payload
        self.m60_status_json = json.dumps(self.m60_status, indent=2)
        self.status_text = str(self.m60_status.get("status_text", "Unknown"))
        self.is_online = bool(self.m60_status.get("is_online", False))
        self.last_updated = str(self.m60_status.get("timestamp", ""))
        poll_delta_seconds = self._poll_delta_seconds(previous_updated, self.last_updated)
        self._apply_phase_payload(self.m60_status, poll_delta_seconds)
        self.active_snmp_version = "v2c" if mp_model == 1 else "v1"
        errors = self.m60_status.get("errors", [])
        self.error = "; ".join(errors) if errors else ""
        self._safe_log_status_snapshot(status_payload)

    def _safe_log_status_snapshot(
        self,
        payload: dict,
        correlation_id: str = "",
        source: str = "poll",
    ):
        try:
            STORE.log_status_snapshot(
                device_ip=self.ip_address.strip(),
                payload=payload,
                correlation_id=correlation_id,
                source=source,
            )
        except Exception:
            # Logging should not block polling/control flows.
            pass

    def _safe_log_command(
        self,
        cmd_type: str,
        value: Any,
        correlation_id: str,
        allowed: bool,
        success: bool,
        error: str,
    ):
        try:
            STORE.log_command(
                CommandAuditRecord(
                    timestamp=datetime.utcnow().isoformat(),
                    correlation_id=correlation_id,
                    device_ip=self.ip_address.strip(),
                    command_type=cmd_type,
                    command_value=value,
                    probe_only=self.safe_command_probe,
                    allowed=allowed,
                    success=success,
                    error=error,
                    actor=self._actor_name(),
                )
            )
        except Exception:
            # Logging should not block command execution paths.
            pass

    def unlock_write_mode(self):
        if not self.is_authenticated:
            self.safety_notice = "Write unlock denied: operator authentication required."
            self.error = self.safety_notice
            return

        success, message, unlock_until = CommandSafetyService.unlock_write_mode(
            operator_key_input=self.operator_key_input,
            requested_seconds=self._write_unlock_seconds(),
        )
        if success:
            self.safe_command_probe = False
            self.write_mode_active = True
            self.write_unlock_until = unlock_until
        else:
            self.safe_command_probe = True
            self.write_mode_active = False
            self.write_unlock_until = ""
        self.safety_notice = message
        self.error = "" if success else message

    def lock_write_mode(self):
        self.safe_command_probe = True
        self.write_mode_active = False
        self.write_unlock_until = ""
        self.safety_notice = "Write mode locked."

    def login_operator(self):
        if self._is_login_locked():
            self.is_authenticated = False
            self.current_operator = ""
            self.auth_notice = "Operator login temporarily locked due to repeated failures."
            self.error = self.auth_notice
            self.login_password_input = ""
            return

        success, message = OperatorAuthService.authenticate(
            username=self.login_username_input,
            password=self.login_password_input,
        )
        self.is_authenticated = success
        if success:
            self.current_operator = self.login_username_input.strip()
            self.auth_notice = f"Authenticated as {self.current_operator}."
            self.error = ""
            self.failed_login_attempts = 0
            self.login_lockout_until = ""
        else:
            self.current_operator = ""
            self.failed_login_attempts += 1
            if self.failed_login_attempts >= self._max_login_attempts():
                lockout_seconds = self._login_lockout_seconds()
                until = datetime.utcnow().timestamp() + lockout_seconds
                self.login_lockout_until = datetime.utcfromtimestamp(until).isoformat()
                self.auth_notice = (
                    "Operator login temporarily locked due to repeated failures."
                )
                self.error = self.auth_notice
            else:
                self.auth_notice = message
                self.error = message
            self.lock_write_mode()
        self.login_password_input = ""

    def logout_operator(self):
        self.is_authenticated = False
        self.current_operator = ""
        self.auth_notice = "Operator not authenticated."
        self.login_password_input = ""
        self.operator_key_input = ""
        self.lock_write_mode()

    def run_retention_cleanup(self):
        if not self.is_authenticated:
            self.maintenance_notice = "Retention cleanup denied: operator authentication required."
            self.error = self.maintenance_notice
            return
        try:
            deleted_commands, deleted_snapshots = MaintenanceService.run_retention_cleanup()
            self.maintenance_notice = (
                f"Retention cleanup complete. Commands deleted: {deleted_commands}, "
                f"snapshots deleted: {deleted_snapshots}."
            )
            self.error = ""
        except Exception as exc:
            self.maintenance_notice = f"Retention cleanup failed: {exc}"
            self.error = self.maintenance_notice
        self.refresh_runtime_health()

    def refresh_runtime_health(self):
        sched = scheduler_status()
        self.retention_scheduler_enabled = bool(sched.get("enabled", False))
        self.retention_scheduler_running = bool(sched.get("running", False))
        interval = sched.get("interval_seconds")
        self.retention_scheduler_interval_text = str(interval) if interval is not None else "unknown"
        self.retention_scheduler_error = str(sched.get("error", "") or "")

        cleanup = MaintenanceService.get_cleanup_status()
        self.last_retention_cleanup_at = str(cleanup.get("last_run_at", ""))
        self.last_retention_cleanup_result = str(
            cleanup.get("message", "No retention cleanup run yet.")
        )

        scheduler_line = (
            f"Scheduler: {'enabled' if self.retention_scheduler_enabled else 'disabled'}, "
            f"{'running' if self.retention_scheduler_running else 'stopped'}, "
            f"interval={self.retention_scheduler_interval_text}s"
        )
        if self.retention_scheduler_error:
            scheduler_line = f"{scheduler_line} ({self.retention_scheduler_error})"

        cleanup_at = self.last_retention_cleanup_at if self.last_retention_cleanup_at else "never"
        self.runtime_health_notice = (
            f"{scheduler_line}. Last cleanup: {cleanup_at}. {self.last_retention_cleanup_result}"
        )

    async def confirm_pending_command(self):
        if not self.pending_command_type:
            self.error = "No pending command to confirm."
            return
        if self._has_expired(self.pending_confirmation_expires):
            self.error = "Confirmation token expired."
            self.pending_confirmation_token = ""
            self.pending_confirmation_expires = ""
            self.pending_command_type = ""
            self.pending_command_value_json = ""
            self.pending_confirmation_notice = ""
            return
        if self.confirmation_input.strip() != self.pending_confirmation_token:
            self.error = "Confirmation token mismatch."
            return

        cmd_type = self.pending_command_type
        value: Any = None
        if self.pending_command_value_json:
            value = json.loads(self.pending_command_value_json)

        self.pending_confirmation_token = ""
        self.pending_confirmation_expires = ""
        self.pending_command_type = ""
        self.pending_command_value_json = ""
        self.pending_confirmation_notice = ""
        self.confirmation_input = ""

        await self.send_command(cmd_type, value, force_confirmed=True)

    async def connect_m60(self):
        await self.add_and_poll_m60()
        if (self.auto_refresh_enabled or self.auto_reconnect_enabled) and not self.auto_refresh_running:
            return TrafficState.auto_refresh_loop

    async def refresh_status(self):
        await self.add_and_poll_m60()

    @rx.event(background=True)
    async def auto_refresh_loop(self):
        """Continuously poll while online and auto-reconnect when offline."""
        async with self:
            if self.auto_refresh_running:
                return
            self.auto_refresh_running = True

        try:
            while True:
                async with self:
                    refresh_enabled = self.auto_refresh_enabled
                    reconnect_enabled = self.auto_reconnect_enabled
                    is_online = self.is_online
                    is_loading = self.is_loading
                    refresh_interval = self._refresh_interval_seconds()
                    reconnect_interval = self._reconnect_interval_seconds()

                    should_continue = refresh_enabled or reconnect_enabled
                if not should_continue:
                    break

                if is_loading:
                    await asyncio.sleep(1.0)
                    continue

                if is_online and refresh_enabled:
                    try:
                        status_payload, mp_model = await self._collect_status_snapshot()
                    except ValueError:
                        async with self:
                            self.m60_status = {
                                "error": "Port, timeout, and retries must be numeric.",
                            }
                            self.m60_status_json = json.dumps(self.m60_status, indent=2)
                            self.error = self.m60_status["error"]
                            self.status_text = "Input validation failed"
                            self.is_online = False
                    except Exception as e:
                        async with self:
                            self.m60_status = {"error": f"Unhandled exception: {e}"}
                            self.m60_status_json = json.dumps(self.m60_status, indent=2)
                            self.error = self.m60_status["error"]
                            self.status_text = "Unhandled exception"
                            self.is_online = False
                    else:
                        async with self:
                            self._apply_status_snapshot(status_payload, mp_model)
                    await asyncio.sleep(refresh_interval)
                    continue

                if (not is_online) and reconnect_enabled:
                    try:
                        status_payload, mp_model = await self._collect_status_snapshot()
                    except ValueError:
                        async with self:
                            self.m60_status = {
                                "error": "Port, timeout, and retries must be numeric.",
                            }
                            self.m60_status_json = json.dumps(self.m60_status, indent=2)
                            self.error = self.m60_status["error"]
                            self.status_text = "Input validation failed"
                            self.is_online = False
                    except Exception as e:
                        async with self:
                            self.m60_status = {"error": f"Unhandled exception: {e}"}
                            self.m60_status_json = json.dumps(self.m60_status, indent=2)
                            self.error = self.m60_status["error"]
                            self.status_text = "Unhandled exception"
                            self.is_online = False
                    else:
                        async with self:
                            self._apply_status_snapshot(status_payload, mp_model)
                    await asyncio.sleep(reconnect_interval)
                    continue

                await asyncio.sleep(1.0)
        finally:
            async with self:
                self.auto_refresh_running = False

    async def add_and_poll_m60(self):
        self.is_loading = True
        try:
            try:
                status_payload, mp_model = await self._collect_status_snapshot()
            except ValueError:
                self.m60_status = {
                    "error": "Port, timeout, and retries must be numeric.",
                }
                self.m60_status_json = json.dumps(self.m60_status, indent=2)
                self.error = self.m60_status["error"]
                self.status_text = "Input validation failed"
                self.is_online = False
                return
            self._apply_status_snapshot(status_payload, mp_model)
        except Exception as e:
            self.m60_status = {"error": f"Unhandled exception: {e}"}
            self.m60_status_json = json.dumps(self.m60_status, indent=2)
            self.error = self.m60_status["error"]
            self.status_text = "Unhandled exception"
            self.is_online = False
        finally:
            self.is_loading = False

    async def send_command(self, cmd_type: str, value: Any, force_confirmed: bool = False):
        """Send timing-related commands to the controller."""
        self.is_loading = True
        correlation_id = uuid4().hex
        try:
            if not self.is_authenticated:
                auth_error = "Command denied: operator authentication required."
                self.error = auth_error
                self._safe_log_command(
                    cmd_type=cmd_type,
                    value=value,
                    correlation_id=correlation_id,
                    allowed=False,
                    success=False,
                    error=auth_error,
                )
                return

            if self._requires_confirmation(cmd_type) and not force_confirmed:
                self._start_command_confirmation(cmd_type, value)
                self.error = self.pending_confirmation_notice
                self._safe_log_command(
                    cmd_type=cmd_type,
                    value=value,
                    correlation_id=correlation_id,
                    allowed=False,
                    success=False,
                    error="Confirmation required before write command execution.",
                )
                return

            safety = CommandSafetyService.evaluate_command(
                safe_command_probe=self.safe_command_probe,
                write_unlock_until=self.write_unlock_until,
            )
            self.safety_notice = safety.reason
            if not safety.allowed:
                self.safe_command_probe = True
                self.write_mode_active = False
                self.write_unlock_until = ""
                self.error = safety.reason
                self._safe_log_command(
                    cmd_type=cmd_type,
                    value=value,
                    correlation_id=correlation_id,
                    allowed=False,
                    success=False,
                    error=safety.reason,
                )
                return

            config = self._build_config()
            success, payload, mp_model, error = await CommandService.execute_siemens_m60_command(
                config=config,
                cmd_type=cmd_type,
                value=value,
                safe_command_probe=self.safe_command_probe,
            )
            self._safe_log_command(
                cmd_type=cmd_type,
                value=value,
                correlation_id=correlation_id,
                allowed=True,
                success=success,
                error=error,
            )
            if success:
                self.m60_status = payload
                self.m60_status_json = json.dumps(self.m60_status, indent=2)
                self.status_text = str(self.m60_status.get("status_text", "Command applied"))
                self.is_online = bool(self.m60_status.get("is_online", False))
                self.last_updated = str(self.m60_status.get("timestamp", ""))
                self._apply_phase_payload(self.m60_status)
                self.active_snmp_version = "v2c" if mp_model == 1 else "v1"
                errors = self.m60_status.get("errors", [])
                self.error = "; ".join(errors) if errors else ""
                self._safe_log_status_snapshot(
                    self.m60_status,
                    correlation_id=correlation_id,
                    source="command",
                )
            else:
                self.m60_status = payload
                self.m60_status_json = json.dumps(self.m60_status, indent=2)
                self.error = error
                self.is_online = bool(self.m60_status.get("is_online", False))
        except Exception as e:
            self.error = str(e)
        finally:
            self.is_loading = False

    async def connect_and_start_polling(self):
        self.refresh_runtime_health()
        return await self.connect_m60()

    async def select_pattern_1(self):
        await self.send_command("select_pattern", 1)

    async def select_pattern_2(self):
        await self.send_command("select_pattern", 2)

    async def set_mode_free(self):
        await self.send_command("set_mode", "free")

    async def set_mode_coordinated(self):
        await self.send_command("set_mode", "coordinated")

    async def manual_hold(self):
        await self.send_command("manual_hold", True)

    async def advance_phase(self):
        await self.send_command("advance_phase", True)