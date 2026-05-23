import json
import asyncio
from datetime import datetime
from typing import Any

import reflex as rx
from .components.device_card import timing_panel
from .models.device import DeviceConfig
from .devices.siemens_m60 import SiemensM60

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
    safe_command_probe: bool = True
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
        device = SiemensM60(config)
        success = await device.connect()
        if success:
            status_payload = (await device.poll()).model_dump(mode="json")
        else:
            status_payload = device.status.model_dump(mode="json")
        mp_model = getattr(device, "_mp_model", 1)
        return status_payload, mp_model

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
            
    async def send_command(self, cmd_type: str, value: Any):
        """Send timing-related commands to the controller."""
        self.is_loading = True
        try:
            config = self._build_config()
            device = SiemensM60(config)
            if not await device.connect():
                self.m60_status = device.status.model_dump(mode="json")
                self.m60_status_json = json.dumps(self.m60_status, indent=2)
                self.error = "Controller connection failed before command"
                self.is_online = False
                return

            success = False
            if cmd_type == "select_pattern":
                success = await device.command(
                    "select_pattern",
                    {"pattern": value, "probe_only": self.safe_command_probe},
                )
                self.error = "" if success else "Failed to select pattern"
            elif cmd_type == "set_mode":
                success = await device.command(
                    "set_mode",
                    {"mode": value, "probe_only": self.safe_command_probe},
                )
            elif cmd_type == "manual_hold":
                success = await device.command(
                    "manual_hold",
                    {"hold": value, "probe_only": self.safe_command_probe},
                )
            elif cmd_type == "advance_phase":
                success = await device.command(
                    "advance_phase",
                    {"probe_only": self.safe_command_probe},
                )
            
            if success:
                self.m60_status = (await device.poll()).model_dump(mode="json")
                self.m60_status_json = json.dumps(self.m60_status, indent=2)
                self.status_text = str(self.m60_status.get("status_text", "Command applied"))
                self.is_online = bool(self.m60_status.get("is_online", False))
                self.last_updated = str(self.m60_status.get("timestamp", ""))
                self._apply_phase_payload(self.m60_status)
                self.active_snmp_version = "v2c" if getattr(device, "_mp_model", 1) == 1 else "v1"
                errors = self.m60_status.get("errors", [])
                self.error = "; ".join(errors) if errors else ""
            else:
                self.error = self.error or f"Command failed: {cmd_type}"
        except Exception as e:
            self.error = str(e)
        finally:
            self.is_loading = False

    async def connect_and_start_polling(self):
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
            
# Example page
def index():
    return rx.vstack(
        rx.heading("Traffic Controller Platform", size="9"),
        rx.hstack(
            rx.input(
                value=TrafficState.ip_address,
                on_change=TrafficState.update_ip_address,
                placeholder="Controller IP",
                width="18em",
            ),
            rx.input(
                value=TrafficState.port_text,
                on_change=TrafficState.update_port_text,
                placeholder="Port",
                width="7em",
            ),
            rx.input(
                value=TrafficState.community,
                on_change=TrafficState.update_community,
                placeholder="SNMP community",
                width="10em",
            ),
            spacing="3",
            wrap="wrap",
        ),
        rx.hstack(
            rx.input(
                value=TrafficState.snmp_version,
                on_change=TrafficState.update_snmp_version,
                placeholder="SNMP version: auto | v2c | v1",
                width="14em",
            ),
            rx.input(
                value=TrafficState.timeout_text,
                on_change=TrafficState.update_timeout_text,
                placeholder="Timeout seconds",
                width="10em",
            ),
            rx.input(
                value=TrafficState.retries_text,
                on_change=TrafficState.update_retries_text,
                placeholder="Retries",
                width="7em",
            ),
            spacing="3",
            wrap="wrap",
        ),
        rx.hstack(
            rx.switch(
                checked=TrafficState.safe_command_probe,
                on_change=TrafficState.update_safe_command_probe,
            ),
            rx.text("Safe Command Probe (no SNMP SET writes)"),
            spacing="2",
            align="center",
        ),
        rx.hstack(
            rx.switch(
                checked=TrafficState.auto_refresh_enabled,
                on_change=TrafficState.update_auto_refresh_enabled,
            ),
            rx.text("Auto Refresh"),
            rx.input(
                value=TrafficState.refresh_interval_text,
                on_change=TrafficState.update_refresh_interval_text,
                placeholder="Seconds",
                width="6em",
            ),
            rx.text("sec"),
            spacing="2",
            align="center",
        ),
        rx.hstack(
            rx.switch(
                checked=TrafficState.auto_reconnect_enabled,
                on_change=TrafficState.update_auto_reconnect_enabled,
            ),
            rx.text("Auto Reconnect"),
            rx.input(
                value=TrafficState.reconnect_interval_text,
                on_change=TrafficState.update_reconnect_interval_text,
                placeholder="Seconds",
                width="6em",
            ),
            rx.text("sec"),
            spacing="2",
            align="center",
        ),
        rx.button("Connect & Poll Siemens M60", on_click=TrafficState.connect_and_start_polling),
        timing_panel(
            TrafficState.current_pattern,
            TrafficState.unit_status,
            TrafficState.green_phases,
            TrafficState.yellow_phases,
            TrafficState.red_phases,
            TrafficState.vehicle_calls,
            TrafficState.ped_calls,
            TrafficState.remaining_time_summary,
            TrafficState.timer_mode_text,
            TrafficState.ring_status_summary,
            TrafficState.ring_status_lines,
            TrafficState.phase_detail_lines,
            TrafficState.status_text,
            TrafficState.select_pattern_1,
            TrafficState.select_pattern_2,
            TrafficState.set_mode_free,
            TrafficState.set_mode_coordinated,
            TrafficState.manual_hold,
            TrafficState.advance_phase,
        ),
        rx.cond(
            TrafficState.m60_status_json != "",
            rx.code_block(TrafficState.m60_status_json, language="json"),
            rx.text("No status yet."),
        ),

        spacing="5",
        padding="2em",
    )

def dashboard():
    return rx.vstack(
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.heading("OpenSignal ITS Controller Console", size="8", color="indigo"),
                    rx.spacer(),
                    rx.button(
                        "Connect",
                        on_click=TrafficState.connect_and_start_polling,
                        is_disabled=TrafficState.is_loading,
                        color_scheme="green",
                        size="3",
                    ),
                    rx.button(
                        "Refresh",
                        on_click=TrafficState.refresh_status,
                        is_disabled=TrafficState.is_loading,
                        size="3",
                    ),
                    width="100%",
                ),
                rx.hstack(
                    rx.badge(
                        rx.cond(TrafficState.is_online, "ONLINE", "OFFLINE"),
                        color_scheme=rx.cond(TrafficState.is_online, "green", "red"),
                    ),
                    rx.badge(f"Pattern {TrafficState.current_pattern}", color_scheme="blue"),
                    rx.badge(f"Unit {TrafficState.unit_status}", color_scheme="gray"),
                    rx.badge(
                        rx.cond(TrafficState.safe_command_probe, "PROBE MODE", "WRITE MODE"),
                        color_scheme=rx.cond(TrafficState.safe_command_probe, "amber", "red"),
                    ),
                    rx.badge(
                        rx.cond(TrafficState.auto_refresh_running, "AUTO REFRESH ON", "AUTO REFRESH OFF"),
                        color_scheme=rx.cond(TrafficState.auto_refresh_running, "green", "gray"),
                    ),
                    rx.badge(
                        rx.cond(TrafficState.auto_reconnect_enabled, "AUTO RECONNECT ON", "AUTO RECONNECT OFF"),
                        color_scheme=rx.cond(TrafficState.auto_reconnect_enabled, "green", "gray"),
                    ),
                    rx.text(f"SNMP {TrafficState.active_snmp_version}"),
                    rx.text(f"Updated: {TrafficState.last_updated}"),
                    spacing="3",
                    wrap="wrap",
                    width="100%",
                ),
                spacing="3",
                width="100%",
            ),
            width="100%",
            padding="4",
        ),
        rx.grid(
            rx.card(
                rx.vstack(
                    rx.heading("Connection & Polling", size="4"),
                    rx.input(
                        value=TrafficState.ip_address,
                        on_change=TrafficState.update_ip_address,
                        placeholder="Controller IP",
                        width="100%",
                    ),
                    rx.hstack(
                        rx.input(
                            value=TrafficState.port_text,
                            on_change=TrafficState.update_port_text,
                            placeholder="Port",
                            width="40%",
                        ),
                        rx.input(
                            value=TrafficState.community,
                            on_change=TrafficState.update_community,
                            placeholder="Community",
                            width="60%",
                        ),
                        width="100%",
                    ),
                    rx.hstack(
                        rx.input(
                            value=TrafficState.timeout_text,
                            on_change=TrafficState.update_timeout_text,
                            placeholder="Timeout sec",
                            width="50%",
                        ),
                        rx.input(
                            value=TrafficState.retries_text,
                            on_change=TrafficState.update_retries_text,
                            placeholder="Retries",
                            width="50%",
                        ),
                        width="100%",
                    ),
                    rx.hstack(
                        rx.switch(
                            checked=TrafficState.auto_refresh_enabled,
                            on_change=TrafficState.update_auto_refresh_enabled,
                        ),
                        rx.text("Auto Refresh"),
                        rx.input(
                            value=TrafficState.refresh_interval_text,
                            on_change=TrafficState.update_refresh_interval_text,
                            width="6em",
                            placeholder="sec",
                        ),
                        spacing="2",
                        align="center",
                        width="100%",
                    ),
                    rx.hstack(
                        rx.switch(
                            checked=TrafficState.auto_reconnect_enabled,
                            on_change=TrafficState.update_auto_reconnect_enabled,
                        ),
                        rx.text("Auto Reconnect"),
                        rx.input(
                            value=TrafficState.reconnect_interval_text,
                            on_change=TrafficState.update_reconnect_interval_text,
                            width="6em",
                            placeholder="sec",
                        ),
                        spacing="2",
                        align="center",
                        width="100%",
                    ),
                    spacing="3",
                    width="100%",
                ),
                width="100%",
                height="100%",
            ),
            rx.card(
                rx.vstack(
                    rx.heading("SEPAC Ring Timer Text View", size="4"),
                    rx.text("Controller-style text status", size="1", color="gray"),
                    rx.code_block(TrafficState.ring_status_console_text, language="log", width="100%"),
                    width="100%",
                    spacing="2",
                ),
                width="100%",
                height="100%",
            ),
            columns="2",
            spacing="4",
            width="100%",
        ),
        rx.cond(
            TrafficState.error != "",
            rx.box(rx.text(TrafficState.error), border="1px solid #fca5a5", bg="#fef2f2", padding="3", border_radius="8px", width="100%"),
            rx.fragment(),
        ),

        spacing="6",
        padding="6",
        width="100%",
        max_width="1400px",
        margin="0 auto",
    )

app = rx.App()
app.add_page(dashboard, route="/", title="OpenSignal ITS")