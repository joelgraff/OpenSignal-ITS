# siemens_m60.py - Siemens M60 ATC device handler with SNMP and Telnet support.

from pysnmp.hlapi.asyncio import UdpTransportTarget
from typing import Dict, Any
import logging
import json
from pathlib import Path
from .base import Device
from ..models.device import DeviceStatus, DeviceConfig
from ..polling_telemetry import POLLING_TELEMETRY
from ..protocols.snmp import SNMPClient


logger = logging.getLogger(__name__)


def _load_oid_reference() -> dict[str, str]:
    """Load OID definitions from docs, with graceful fallback to hardcoded defaults."""
    docs_dir = Path(__file__).resolve().parent.parent / "docs"
    candidates = [
        docs_dir / "M60_OID_REFERENCE.json",
        docs_dir / "m60_oid_table.json",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text())
            mapping: dict[str, str] = {}
            for item in payload.get("oids", []):
                name = str(item.get("name", "")).strip()
                oid = str(item.get("oid", "")).strip()
                if name and oid:
                    mapping[name] = oid
            if mapping:
                logger.info("Loaded %s OID entries from %s", len(mapping), path.name)
                return mapping
        except Exception:
            logger.exception("Failed parsing OID reference file: %s", path)
    return {}


_OID_REF = _load_oid_reference()


def _oid(name: str, fallback: str) -> str:
    return _OID_REF.get(name, fallback)

# Confirmed working objects from SEPAC 5.2.0 walk and SNMPv1 probe.
OID_SYS_DESCR = _oid("sysDescr", "1.3.6.1.2.1.1.1.0")
OID_CURRENT_PATTERN = _oid("currentPattern", "1.3.6.1.4.1.1206.2.2.1.1.9.0")
OID_UNIT_STATUS = _oid("unitControlStatus", "1.3.6.1.4.1.1206.2.2.1.1.7.0")
# Known-good table templates observed on target walk (SEPAC 5.2.0).
OID_PHASE_STATUS_TEMPLATE = _oid("phaseStatusLive", "1.3.6.1.4.1.1206.3.3.1.1.1.1.8.{phase}")
OID_VEH_CALL_TEMPLATE = _oid("vehicleCallLive", "1.3.6.1.4.1.1206.3.3.1.1.3.1.2.2.{phase}")
OID_PED_CALL_TEMPLATE = _oid("pedCallLive", "1.3.6.1.4.1.1206.3.3.1.1.3.1.3.2.{phase}")
OID_TIME_REMAINING_TEMPLATE = _oid("timerLive", "1.3.6.1.4.1.1206.3.3.1.1.3.1.5.2.{phase}")
OID_PHASE_MAX_GREEN_1_TEMPLATE = _oid("phaseMaximum1", "1.3.6.1.4.1.1206.4.2.1.1.2.1.6.{phase}")
OID_RING_STATUS_TEMPLATE = _oid("ringStatus", "1.3.6.1.4.1.1206.4.2.1.7.6.1.1.{ring}")
OID_PHASE_GREENS_GROUP_TEMPLATE = _oid("phaseStatusGroupGreens", "1.3.6.1.4.1.1206.4.2.1.1.4.1.4.{group}")
OID_PHASE_REDS_GROUP_TEMPLATE = _oid("phaseStatusGroupReds", "1.3.6.1.4.1.1206.4.2.1.1.4.1.2.{group}")
OID_PHASE_VEH_CALL_GROUP_TEMPLATE = _oid("phaseStatusGroupVehCalls", "1.3.6.1.4.1.1206.4.2.1.1.4.1.8.{group}")
OID_PHASE_PED_CALL_GROUP_TEMPLATE = _oid("phaseStatusGroupPedCalls", "1.3.6.1.4.1.1206.4.2.1.1.4.1.9.{group}")

# Reference templates from docs (used only if walk-confirmed templates fail).
OID_PHASE_STATUS_TEMPLATE_REF = _oid("phaseStatusGroup", "1.3.6.1.4.1.1206.3.3.1.1.1.1.1.{phase}")
OID_VEH_CALL_TEMPLATE_REF = _oid("vehicleCall", "1.3.6.1.4.1.1206.3.3.1.1.3.1.2.{phase}")
OID_PED_CALL_TEMPLATE_REF = _oid("pedCall", "1.3.6.1.4.1.1206.3.3.1.1.3.1.3.{phase}")
OID_TIME_REMAINING_TEMPLATE_REF = _oid("timeToChange", "1.3.6.1.4.1.1206.3.3.1.1.5.2.{phase}")

# NTCIP 1202 timing/control objects (common scalar controls).
# NOTE: Vendor implementations can vary. Validate on target Siemens M60 docs before production rollout.
OID_SYSTEM_PATTERN_CONTROL = "1.3.6.1.4.1.1206.4.2.1.8.0"
OID_PHASE_CONTROL_HOLD = "1.3.6.1.4.1.1206.4.2.1.9.0"
OID_PHASE_CONTROL_FORCEOFF = "1.3.6.1.4.1.1206.4.2.1.10.0"
OID_PHASE_CONTROL_OMIT = "1.3.6.1.4.1.1206.4.2.1.11.0"


class SiemensM60(Device):
    """Siemens M60 / SEPAC 5.2.0 SNMPv1 polling + legacy command path."""

    device_type = "siemens_m60"

    def __init__(self, config: DeviceConfig):
        super().__init__(config)
        self._snmp = SNMPClient(config)
        self._mp_model = 0  # SNMPv1 is known-good for this controller.
        self._poll_telemetry: dict[str, Any] | None = None
        self._poll_telemetry_section: str | None = None
        self._cached_sys_descr: str | None = None
        self._cached_phase_max_green_1: dict[int, int] = {}

    def _begin_poll_telemetry(self) -> dict[str, Any]:
        return {
            "request_count": 0,
            "object_count": 0,
            "round_trip_count": 0,
            "sections": {
                "identity": 0,
                "ring_status": 0,
                "group_masks": 0,
                "phase_grid": 0,
            },
            "poll_shape": {
                "section_order": ["identity", "ring_status", "group_masks", "phase_grid"],
                "rings": 2,
                "groups": 2,
                "phases": 16,
                "reads_per_phase": 3,
                "expected_request_count": 61,
            },
        }

    def _record_poll_request(self, count: int = 1) -> None:
        telemetry = self._poll_telemetry
        if telemetry is None:
            return
        telemetry["request_count"] = int(telemetry.get("request_count", 0)) + count
        telemetry["object_count"] = int(telemetry.get("object_count", 0)) + count
        section = self._poll_telemetry_section
        if section is None:
            return
        sections = telemetry.setdefault("sections", {})
        sections[section] = int(sections.get(section, 0)) + count

    def _record_poll_round_trip(self) -> None:
        telemetry = self._poll_telemetry
        if telemetry is None:
            return
        telemetry["round_trip_count"] = int(telemetry.get("round_trip_count", 0)) + 1

    async def _read_phase_max_green_1(self, target: UdpTransportTarget, phase: int) -> int | None:
        if phase in self._cached_phase_max_green_1:
            return self._cached_phase_max_green_1[phase]

        phase_max_green_oid = OID_PHASE_MAX_GREEN_1_TEMPLATE.format(phase=phase)
        value = self._to_int(await self._safe_get_oid(target, phase_max_green_oid))
        if value is None:
            return None

        self._cached_phase_max_green_1[phase] = value
        return value

    async def _safe_get_oids(
        self,
        target: UdpTransportTarget,
        oids: list[str],
    ) -> list[str | None] | None:
        if not oids:
            return []
        self._record_poll_round_trip()
        try:
            values, error = await self._snmp.get_oids(
                oids=oids,
                mp_model=self._mp_model,
                target=target,
            )
            if error:
                logger.warning(
                    "SiemensM60 GET batch failed ip=%s oids=%s error=%s",
                    self.config.ip_address,
                    oids,
                    error,
                )
                return None
            if any(value is None for value in values):
                logger.warning(
                    "SiemensM60 GET batch returned missing values ip=%s oids=%s",
                    self.config.ip_address,
                    oids,
                )
                return None
            self._record_poll_request(len(oids))
            return values
        except Exception:
            logger.exception(
                "SiemensM60 GET batch exception ip=%s oids=%s",
                self.config.ip_address,
                oids,
            )
            return None

    async def _read_phase_status(self, target: UdpTransportTarget, phase: int) -> int | None:
        status_oid = OID_PHASE_STATUS_TEMPLATE.format(phase=phase)
        status_val = self._to_int(await self._safe_get_oid(target, status_oid))
        if status_val is None:
            status_oid = OID_PHASE_STATUS_TEMPLATE_REF.format(phase=phase)
            status_val = self._to_int(await self._safe_get_oid(target, status_oid))
        return status_val

    async def _read_phase_time_remaining(self, target: UdpTransportTarget, phase: int) -> int | None:
        timer_oid = OID_TIME_REMAINING_TEMPLATE.format(phase=phase)
        timer_val = self._to_int(await self._safe_get_oid(target, timer_oid))
        if timer_val is None:
            timer_oid = OID_TIME_REMAINING_TEMPLATE_REF.format(phase=phase)
            timer_val = self._to_int(await self._safe_get_oid(target, timer_oid))
        return timer_val

    async def _safe_get_oid(self, target: UdpTransportTarget, oid: str) -> str | None:
        """Read one OID and return value as string or None on timeout/noSuchName."""
        try:
            self._record_poll_request()
            self._record_poll_round_trip()
            value, error = await self._snmp.get_oid(
                oid=oid,
                mp_model=self._mp_model,
                target=target,
            )
            if error:
                logger.warning(
                    "SiemensM60 GET failed ip=%s oid=%s error=%s",
                    self.config.ip_address,
                    oid,
                    error,
                )
                return None
            return value
        except Exception:
            logger.exception(
                "SiemensM60 GET exception ip=%s oid=%s",
                self.config.ip_address,
                oid,
            )
            return None

    @staticmethod
    def _to_int(value: str | None) -> int | None:
        if value is None:
            return None
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _unit_status_text(code: int | None) -> str:
        mapping = {
            1: "normal",
            2: "flash",
            3: "preempt",
            4: "stop time",
        }
        if code is None:
            return "unknown"
        return mapping.get(code, f"code {code}")

    @staticmethod
    def _decode_ring_status(code: int | None) -> dict[str, Any]:
        """Decode NTCIP ringStatus bitfield into timer state and event flags."""
        if code is None:
            return {
                "raw": None,
                "state_code": None,
                "state_name": "Unavailable",
                "bit_a": None,
                "bit_b": None,
                "bit_c": None,
                "gap_out": False,
                "max_out": False,
                "force_off": False,
            }

        state_lookup = {
            0: "Min Green",
            1: "Extension",
            2: "Maximum",
            3: "Green Rest",
            4: "Yellow Change",
            5: "Red Clearance",
            6: "Red Rest",
            7: "Undefined",
        }
        state_code = code & 0b111
        return {
            "raw": code,
            "state_code": state_code,
            "state_name": state_lookup.get(state_code, "Unknown"),
            "bit_a": bool(code & 0b0001),
            "bit_b": bool(code & 0b0010),
            "bit_c": bool(code & 0b0100),
            "gap_out": bool(code & 0b1000),
            "max_out": bool(code & 0b1_0000),
            "force_off": bool(code & 0b10_0000),
        }

    @staticmethod
    def _decode_phase_group_bits(mask: int | None, group: int) -> set[int]:
        """Decode NTCIP phase status group bitmask into absolute phase numbers."""
        if mask is None:
            return set()
        base_phase = 1 if group == 1 else 9
        active: set[int] = set()
        for bit in range(8):
            if mask & (1 << bit):
                active.add(base_phase + bit)
        return active

    async def _read_group_mask(
        self,
        target: UdpTransportTarget,
        template: str,
        group: int,
    ) -> int | None:
        """Read a grouped NTCIP object with scalar fallback for group 1 devices."""
        if "{group}" in template:
            oid = template.format(group=group)
            value = self._to_int(await self._safe_get_oid(target, oid))
            if value is not None:
                return value
            if group == 1:
                scalar_oid = template.replace(".{group}", "")
                return self._to_int(await self._safe_get_oid(target, scalar_oid))
            return None
        if group != 1:
            return None
        return self._to_int(await self._safe_get_oid(target, template))

    async def connect(self) -> bool:
        """Test connectivity via SNMP."""
        try:
            self.status.errors = []
            target = await self._snmp.create_target()
            sys_descr = None
            current_pattern = None

            connect_values = await self._safe_get_oids(target, [OID_SYS_DESCR, OID_CURRENT_PATTERN])
            if connect_values is not None and all(value is not None for value in connect_values):
                sys_descr, current_pattern = connect_values

            if sys_descr is None and current_pattern is None:
                sys_descr = await self._safe_get_oid(target, OID_SYS_DESCR)
                current_pattern = await self._safe_get_oid(target, OID_CURRENT_PATTERN)

            if sys_descr is None and current_pattern is None:
                self.status.is_online = False
                self.status.status_text = "SNMPv1 connection failed"
                self.status.errors.append("No response from sysDescr/currentPattern")
                return False

            self.status.is_online = True
            self.status.status_text = "Connected via SNMP v1"
            logger.info(
                "SiemensM60 connect success ip=%s port=%s version=v1",
                self.config.ip_address,
                self.config.port,
            )
            return True
        except Exception as e:
            self.status.is_online = False
            self.status.status_text = "SNMP connect exception"
            self.status.errors.append(str(e))
            return False

    async def poll(self) -> DeviceStatus:
        """Poll known-good OIDs and return structured status for UI."""
        telemetry = self._begin_poll_telemetry()
        self._poll_telemetry = telemetry
        runtime_key = getattr(self, "_runtime_key", "") or (
            f"{self.device_type or self.__class__.__name__.lower()}::{self.status.device_id}"
        )
        async with POLLING_TELEMETRY.observe(
            runtime_key,
            "SiemensM60.poll",
            track_overlap=False,
        ):
            try:
                self.status.errors = []
                target = await self._snmp.create_target()

                self._poll_telemetry_section = "identity"
                sys_descr = self._cached_sys_descr
                if sys_descr is None:
                    sys_descr = await self._safe_get_oid(target, OID_SYS_DESCR)
                    if sys_descr is not None:
                        self._cached_sys_descr = sys_descr

                identity_values = await self._safe_get_oids(target, [OID_CURRENT_PATTERN, OID_UNIT_STATUS])
                if identity_values is None:
                    current_pattern_raw = await self._safe_get_oid(target, OID_CURRENT_PATTERN)
                    unit_status_raw = await self._safe_get_oid(target, OID_UNIT_STATUS)
                else:
                    current_pattern_raw, unit_status_raw = identity_values

                self._poll_telemetry_section = "ring_status"
                ring_status: dict[str, dict[str, Any]] = {}
                ring_state_parts: list[str] = []
                ring_oids = [
                    OID_RING_STATUS_TEMPLATE.format(ring=ring)
                    if "{ring}" in OID_RING_STATUS_TEMPLATE
                    else OID_RING_STATUS_TEMPLATE
                    for ring in (1, 2)
                ]
                ring_values = await self._safe_get_oids(target, ring_oids)
                if ring_values is None:
                    ring_values = []
                    for ring in (1, 2):
                        ring_oid = (
                            OID_RING_STATUS_TEMPLATE.format(ring=ring)
                            if "{ring}" in OID_RING_STATUS_TEMPLATE
                            else OID_RING_STATUS_TEMPLATE
                        )
                        ring_values.append(await self._safe_get_oid(target, ring_oid))
                for ring, ring_raw in enumerate(ring_values, start=1):
                    decoded = self._decode_ring_status(self._to_int(ring_raw))
                    ring_status[str(ring)] = decoded
                    ring_state_parts.append(f"R{ring}:{decoded['state_name']}")

                self._poll_telemetry_section = "group_masks"
                ntcip_greens: set[int] = set()
                ntcip_reds: set[int] = set()
                ntcip_veh_calls: set[int] = set()
                ntcip_ped_calls: set[int] = set()
                has_ntcip_greens = False
                has_ntcip_reds = False
                has_ntcip_veh_calls = False
                has_ntcip_ped_calls = False
                ntcip_masks: dict[str, dict[str, int | None]] = {
                    "greens": {},
                    "reds": {},
                    "veh_calls": {},
                    "ped_calls": {},
                }

                group_mask_oids = [
                    OID_PHASE_GREENS_GROUP_TEMPLATE.format(group=group)
                    for group in (1, 2)
                ] + [
                    OID_PHASE_REDS_GROUP_TEMPLATE.format(group=group)
                    for group in (1, 2)
                ] + [
                    OID_PHASE_VEH_CALL_GROUP_TEMPLATE.format(group=group)
                    for group in (1, 2)
                ] + [
                    OID_PHASE_PED_CALL_GROUP_TEMPLATE.format(group=group)
                    for group in (1, 2)
                ]
                group_mask_values = await self._safe_get_oids(target, group_mask_oids)
                if group_mask_values is None:
                    for group in (1, 2):
                        green_mask = await self._read_group_mask(target, OID_PHASE_GREENS_GROUP_TEMPLATE, group)
                        red_mask = await self._read_group_mask(target, OID_PHASE_REDS_GROUP_TEMPLATE, group)
                        veh_mask = await self._read_group_mask(target, OID_PHASE_VEH_CALL_GROUP_TEMPLATE, group)
                        ped_mask = await self._read_group_mask(target, OID_PHASE_PED_CALL_GROUP_TEMPLATE, group)

                        ntcip_masks["greens"][str(group)] = green_mask
                        ntcip_masks["reds"][str(group)] = red_mask
                        ntcip_masks["veh_calls"][str(group)] = veh_mask
                        ntcip_masks["ped_calls"][str(group)] = ped_mask

                        if green_mask is not None:
                            has_ntcip_greens = True
                            ntcip_greens |= self._decode_phase_group_bits(green_mask, group)
                        if red_mask is not None:
                            has_ntcip_reds = True
                            ntcip_reds |= self._decode_phase_group_bits(red_mask, group)
                        if veh_mask is not None:
                            has_ntcip_veh_calls = True
                            ntcip_veh_calls |= self._decode_phase_group_bits(veh_mask, group)
                        if ped_mask is not None:
                            has_ntcip_ped_calls = True
                            ntcip_ped_calls |= self._decode_phase_group_bits(ped_mask, group)
                else:
                    green_values = group_mask_values[0:2]
                    red_values = group_mask_values[2:4]
                    veh_values = group_mask_values[4:6]
                    ped_values = group_mask_values[6:8]
                    for index, group in enumerate((1, 2)):
                        green_mask = self._to_int(green_values[index])
                        red_mask = self._to_int(red_values[index])
                        veh_mask = self._to_int(veh_values[index])
                        ped_mask = self._to_int(ped_values[index])

                        ntcip_masks["greens"][str(group)] = green_mask
                        ntcip_masks["reds"][str(group)] = red_mask
                        ntcip_masks["veh_calls"][str(group)] = veh_mask
                        ntcip_masks["ped_calls"][str(group)] = ped_mask

                        if green_mask is not None:
                            has_ntcip_greens = True
                            ntcip_greens |= self._decode_phase_group_bits(green_mask, group)
                        if red_mask is not None:
                            has_ntcip_reds = True
                            ntcip_reds |= self._decode_phase_group_bits(red_mask, group)
                        if veh_mask is not None:
                            has_ntcip_veh_calls = True
                            ntcip_veh_calls |= self._decode_phase_group_bits(veh_mask, group)
                        if ped_mask is not None:
                            has_ntcip_ped_calls = True
                            ntcip_ped_calls |= self._decode_phase_group_bits(ped_mask, group)

                has_ntcip_veh_calls = all(mask is not None for mask in ntcip_masks["veh_calls"].values())
                has_ntcip_ped_calls = all(mask is not None for mask in ntcip_masks["ped_calls"].values())

                self._poll_telemetry_section = "phase_grid"
                phases: dict[str, dict[str, Any]] = {}
                raw_phase_status: dict[str, int] = {}
                active_vehicle_calls: list[int] = []
                active_ped_calls: list[int] = []
                green_phases: list[int] = []
                yellow_phases: list[int] = []
                red_phases: list[int] = []
                time_remaining: dict[str, int] = {}
                phase_max_green_1: dict[str, int] = {}

                phase_status_oids = [OID_PHASE_STATUS_TEMPLATE.format(phase=phase) for phase in range(1, 17)]
                phase_status_values = await self._safe_get_oids(target, phase_status_oids)
                if phase_status_values is None:
                    phase_status_values = [await self._read_phase_status(target, phase) for phase in range(1, 17)]

                timer_oids = [OID_TIME_REMAINING_TEMPLATE.format(phase=phase) for phase in range(1, 17)]
                timer_values = await self._safe_get_oids(target, timer_oids)
                if timer_values is None:
                    timer_values = [await self._read_phase_time_remaining(target, phase) for phase in range(1, 17)]

                for phase in range(1, 17):
                    status_val = self._to_int(phase_status_values[phase - 1]) or 0

                    veh_call_oid = OID_VEH_CALL_TEMPLATE.format(phase=phase)
                    ped_call_oid = OID_PED_CALL_TEMPLATE.format(phase=phase)

                    if has_ntcip_veh_calls:
                        veh_call_val = 0
                    else:
                        veh_call_val = self._to_int(await self._safe_get_oid(target, veh_call_oid))
                        if veh_call_val is None:
                            veh_call_oid = OID_VEH_CALL_TEMPLATE_REF.format(phase=phase)
                            veh_call_val = self._to_int(await self._safe_get_oid(target, veh_call_oid))

                    if has_ntcip_ped_calls:
                        ped_call_val = 0
                    else:
                        ped_call_val = self._to_int(await self._safe_get_oid(target, ped_call_oid))
                        if ped_call_val is None:
                            ped_call_oid = OID_PED_CALL_TEMPLATE_REF.format(phase=phase)
                            ped_call_val = self._to_int(await self._safe_get_oid(target, ped_call_oid))

                    timer_val = self._to_int(timer_values[phase - 1]) or 0
                    max_green_1_val = await self._read_phase_max_green_1(target, phase)

                    veh_call_val = veh_call_val or 0
                    ped_call_val = ped_call_val or 0
                    max_green_1_val = max_green_1_val or 0

                    is_green = bool(status_val & 0b0001)
                    is_yellow = bool(status_val & 0b0010)
                    is_red = bool(status_val & 0b0100)
                    has_veh_call = veh_call_val != 0
                    has_ped_call = ped_call_val != 0

                    if has_ntcip_greens:
                        is_green = phase in ntcip_greens
                    if has_ntcip_reds:
                        is_red = phase in ntcip_reds
                    if has_ntcip_veh_calls:
                        has_veh_call = phase in ntcip_veh_calls
                    if has_ntcip_ped_calls:
                        has_ped_call = phase in ntcip_ped_calls

                    if is_green:
                        green_phases.append(phase)
                    if is_yellow:
                        yellow_phases.append(phase)
                    if is_red:
                        red_phases.append(phase)
                    if has_veh_call:
                        active_vehicle_calls.append(phase)
                    if has_ped_call:
                        active_ped_calls.append(phase)

                    phase_key = str(phase)
                    raw_phase_status[phase_key] = status_val
                    time_remaining[phase_key] = timer_val
                    phase_max_green_1[phase_key] = max_green_1_val
                    phases[phase_key] = {
                        "green": is_green,
                        "yellow": is_yellow,
                        "red": is_red,
                        "vehicle_call": has_veh_call,
                        "ped_call": has_ped_call,
                        "time_remaining": timer_val,
                        "max_green_1": max_green_1_val,
                        "raw_status": status_val,
                    }

                current_pattern = self._to_int(current_pattern_raw)
                unit_status_code = self._to_int(unit_status_raw)
                phase_summary = {
                    "green": green_phases,
                    "yellow": yellow_phases,
                    "red": red_phases,
                    "vehicle_calls": active_vehicle_calls,
                    "ped_calls": active_ped_calls,
                }

                self.status.extra = {
                    "current_pattern": current_pattern or 0,
                    "unit_status": unit_status_code or 0,
                    "phases": phases,
                    "timers": time_remaining,
                    "phase_max_green_1": phase_max_green_1,
                    "phase_summary": phase_summary,
                    "ring_status": ring_status,
                    "ring_status_summary": ", ".join(ring_state_parts) if ring_state_parts else "none",
                    "ntcip_phase_group_masks": ntcip_masks,
                    "poll_telemetry": telemetry,
                }

                self.status.raw_data = {
                    "sys_descr": sys_descr or "unavailable",
                    "current_pattern": str(current_pattern) if current_pattern is not None else "Unknown",
                    "unit_status_code": unit_status_code,
                    "unit_status": self._unit_status_text(unit_status_code),
                    "phase_status": raw_phase_status,
                    "green_phases": ", ".join(str(p) for p in green_phases) if green_phases else "none",
                    "yellow_phases": ", ".join(str(p) for p in yellow_phases) if yellow_phases else "none",
                    "red_phases": ", ".join(str(p) for p in red_phases) if red_phases else "none",
                    "vehicle_calls": ", ".join(str(p) for p in active_vehicle_calls) if active_vehicle_calls else "none",
                    "ped_calls": ", ".join(str(p) for p in active_ped_calls) if active_ped_calls else "none",
                    "time_remaining": time_remaining,
                    "phase_max_green_1": phase_max_green_1,
                    "ring_status": ring_status,
                    "ring_status_summary": ", ".join(ring_state_parts) if ring_state_parts else "none",
                    "ntcip_phase_group_masks": ntcip_masks,
                }

                if current_pattern is None and unit_status_code is None and sys_descr is None:
                    self.status.is_online = False
                    self.status.status_text = "SNMPv1 poll failed"
                    self.status.errors.append("No values returned from known-good OIDs")
                    return self.status

                self.status.is_online = True
                pattern_text = self.status.raw_data.get("current_pattern", "Unknown")
                unit_text = self.status.raw_data.get("unit_status", "unknown")
                self.status.status_text = f"Online - Pattern {pattern_text}, Unit {unit_text}"
                logger.info(
                    "SiemensM60 poll success ip=%s pattern=%s unit_status=%s",
                    self.config.ip_address,
                    pattern_text,
                    unit_text,
                )
                return self.status

            except Exception as e:
                logger.exception("SiemensM60 poll exception ip=%s", self.config.ip_address)
                self.status.errors.append(str(e))
                self.status.is_online = False
                self.status.status_text = "SNMPv1 poll exception"
                return self.status

    async def command(self, command: str, params: Dict[str, Any]) -> bool:
        """Execute timing and control commands."""
        try:
            probe_only = bool(params.get("probe_only", False))

            if command == "select_pattern":
                pattern = int(params.get("pattern", 1))
                # NTCIP 1202: systemPatternControl
                if probe_only:
                    return await self._probe_command_target(
                        OID_SYSTEM_PATTERN_CONTROL,
                        f"Probe pattern command value={pattern}",
                    )
                success = await self._set_snmp(OID_SYSTEM_PATTERN_CONTROL, pattern)
                if success:
                    self.status.status_text = f"Pattern {pattern} selected"
                return success

            if command == "set_mode":
                mode = str(params.get("mode", "")).lower()
                # Common pattern control mapping: 1=free, 2=coordinated.
                mode_value = 2 if mode == "coordinated" else 1
                if probe_only:
                    return await self._probe_command_target(
                        OID_SYSTEM_PATTERN_CONTROL,
                        f"Probe mode command mode={mode or 'unknown'} value={mode_value}",
                    )
                success = await self._set_snmp(OID_SYSTEM_PATTERN_CONTROL, mode_value)
                if success:
                    self.status.status_text = f"Mode set to {mode or 'unknown'}"
                return success

            if command == "manual_hold":
                hold = bool(params.get("hold", True))
                # NTCIP 1202: phaseControlHold bitmask control.
                if probe_only:
                    return await self._probe_command_target(
                        OID_PHASE_CONTROL_HOLD,
                        f"Probe manual_hold command hold={hold}",
                    )
                if not bool(params.get("allow_all_phases", False)):
                    self.status.errors.append(
                        "manual_hold blocked: allow_all_phases=True required for write mode"
                    )
                    self.status.status_text = "Manual hold blocked by safety gate"
                    return False
                success = await self._set_snmp(OID_PHASE_CONTROL_HOLD, 255 if hold else 0)
                if success:
                    self.status.status_text = "Manual hold command sent"
                return success

            if command == "advance_phase":
                # NTCIP 1202: phaseControlForceOff bitmask control.
                if probe_only:
                    return await self._probe_command_target(
                        OID_PHASE_CONTROL_FORCEOFF,
                        "Probe advance_phase command",
                    )
                if not bool(params.get("allow_all_phases", False)):
                    self.status.errors.append(
                        "advance_phase blocked: allow_all_phases=True required for write mode"
                    )
                    self.status.status_text = "Advance phase blocked by safety gate"
                    return False
                success = await self._set_snmp(OID_PHASE_CONTROL_FORCEOFF, 255)
                if success:
                    self.status.status_text = "Advance phase command sent"
                return success

            self.status.errors.append(f"Unknown command: {command}")
            return False
        except Exception as e:
            self.status.errors.append(str(e))
            return False

    async def _probe_command_target(self, oid: str, label: str) -> bool:
        """Safely validate command target OID existence with GET only (no writes)."""
        target = await self._snmp.create_target()
        result = await self._snmp.probe_oid(
            oid=oid,
            mp_model=self._mp_model,
            target=target,
        )
        probe_ok = bool(result["exists"])
        current_value = result["value"]
        self.status.raw_data["last_command_probe"] = {
            "label": label,
            "oid": oid,
            "exists": probe_ok,
            "current_value": current_value,
            "error": result.get("error"),
        }
        if probe_ok:
            self.status.status_text = f"Probe OK for {oid}"
            return True
        self.status.errors.append(f"Probe failed for {oid}")
        self.status.status_text = f"Probe failed for {oid}"
        return False

    async def _set_snmp(self, oid: str, value: int) -> bool:
        """Helper for SNMP SET operations."""
        try:
            logger.info(
                "SiemensM60 SET attempt ip=%s oid=%s value=%s",
                self.config.ip_address,
                oid,
                value,
            )
            target = await self._snmp.create_target()
            success, error = await self._snmp.set_int(
                oid=oid,
                value=value,
                mp_model=self._mp_model,
                target=target,
            )
            if not success:
                logger.warning(
                    "SiemensM60 SET failed ip=%s oid=%s value=%s error=%s",
                    self.config.ip_address,
                    oid,
                    value,
                    error,
                )
                self.status.errors.append(str(error))
                return False
            logger.info(
                "SiemensM60 SET success ip=%s oid=%s value=%s",
                self.config.ip_address,
                oid,
                value,
            )
            return True
        except Exception as e:
            logger.exception(
                "SiemensM60 SET exception ip=%s oid=%s value=%s",
                self.config.ip_address,
                oid,
                value,
            )
            self.status.errors.append(str(e))
            return False