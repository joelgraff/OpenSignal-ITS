"""Siemens M60 view-model parser for normalized device payloads."""

from __future__ import annotations

from typing import Any


def build_siemens_m60_view(
    payload: dict,
    poll_delta_seconds: int,
    previous_phase_state_age: dict[str, int],
    previous_phase_signatures: dict[str, str],
    previous_ring_raw: dict[str, int],
    previous_ring_age: dict[str, int],
    previous_timer_snapshot: dict[str, int],
) -> dict[str, Any]:
    raw_data = payload.get("raw_data", {}) if isinstance(payload, dict) else {}
    extra = payload.get("extra", {}) if isinstance(payload, dict) else {}

    current_pattern = str(raw_data.get("current_pattern", "Unknown"))
    unit_status = str(raw_data.get("unit_status", "unknown"))

    summary = extra.get("phase_summary", {}) if isinstance(extra, dict) else {}
    greens = summary.get("green", []) if isinstance(summary, dict) else []
    yellows = summary.get("yellow", []) if isinstance(summary, dict) else []
    reds = summary.get("red", []) if isinstance(summary, dict) else []
    veh_calls = summary.get("vehicle_calls", []) if isinstance(summary, dict) else []
    ped_calls = summary.get("ped_calls", []) if isinstance(summary, dict) else []

    green_phases = ", ".join(str(v) for v in greens) if greens else "none"
    yellow_phases = ", ".join(str(v) for v in yellows) if yellows else "none"
    red_phases = ", ".join(str(v) for v in reds) if reds else "none"
    vehicle_calls = ", ".join(str(v) for v in veh_calls) if veh_calls else "none"
    ped_calls = ", ".join(str(v) for v in ped_calls) if ped_calls else "none"

    phases = extra.get("phases", {}) if isinstance(extra, dict) else {}
    lines: list[str] = []
    timer_parts: list[str] = []
    estimated_countdown_parts: list[str] = []
    timer_snapshot: dict[str, int] = {}
    next_phase_state_age: dict[str, int] = dict(previous_phase_state_age)
    next_phase_signatures: dict[str, str] = dict(previous_phase_signatures)
    phase_data: dict[str, dict[str, bool | int]] = {}
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
            previous_signature = previous_phase_signatures.get(phase_key, "")
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

    def _phase_char(phase: int, mode: str) -> str:
        entry = phase_data.get(f"Phase_{phase}", {})
        if not isinstance(entry, dict):
            entry = {}
        is_green = bool(entry.get("green", False))
        is_yellow = bool(entry.get("yellow", False))
        has_veh = bool(entry.get("vehicle_call", False))
        has_ped = bool(entry.get("ped_call", False))
        if mode == "on":
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
        for p in range(start_phase, end_phase + 1):
            entry = phase_data.get(f"Phase_{p}", {})
            if not isinstance(entry, dict):
                continue
            if bool(entry.get("green", False)) or bool(entry.get("yellow", False)):
                return int(entry.get("time_remaining", 0) or 0)
        return 0

    if estimated_countdown_parts:
        remaining_time_summary = ", ".join(estimated_countdown_parts)
        timer_mode_text = "estimated countdown (max green)"
    else:
        remaining_time_summary = ", ".join(timer_parts) if timer_parts else "none"
        if previous_timer_snapshot:
            timer_mode_text = "dynamic" if previous_timer_snapshot != timer_snapshot else "static"
        else:
            timer_mode_text = "unknown"

    ring_status = extra.get("ring_status", {}) if isinstance(extra, dict) else {}
    ring_lines: list[str] = []
    ring_parts: list[str] = []
    next_ring_raw: dict[str, int] = {}
    next_ring_age: dict[str, int] = dict(previous_ring_age)
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
            prev_raw = previous_ring_raw.get(str(ring), -2)
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

    ring_status_summary = ", ".join(ring_parts) if ring_parts else "unknown"

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
        ring_status_console_text = "\n".join([
            *m60_header,
            "Ring raw code bits state            age gap max force",
            *ring_lines,
            "",
            *code_legend,
        ])
    else:
        ring_status_console_text = "\n".join([
            *m60_header,
            "(no data)",
        ])

    return {
        "current_pattern": current_pattern,
        "unit_status": unit_status,
        "green_phases": green_phases,
        "yellow_phases": yellow_phases,
        "red_phases": red_phases,
        "vehicle_calls": vehicle_calls,
        "ped_calls": ped_calls,
        "phase_data": phase_data,
        "phase_current_pattern": current_pattern,
        "phase_unit_control_status": unit_status,
        "phase_detail_lines": lines,
        "phase_state_age_seconds": next_phase_state_age,
        "last_phase_state_signature": next_phase_signatures,
        "remaining_time_summary": remaining_time_summary,
        "timer_mode_text": timer_mode_text,
        "last_timer_snapshot": timer_snapshot,
        "last_ring_status_raw": next_ring_raw,
        "ring_state_age_seconds": next_ring_age,
        "ring_status_summary": ring_status_summary,
        "ring_status_lines": ring_lines,
        "ring_status_console_text": ring_status_console_text,
    }
