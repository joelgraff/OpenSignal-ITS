# siemens_m60.py - Siemens M60 ATC device handler with SNMP and Telnet support.

from pysnmp.hlapi.asyncio import (
    CommunityData,
    ContextData,
    Integer32,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    get_cmd,
    set_cmd,
)
from typing import Dict, Any
import logging
from .base import Device
from ..models.device import DeviceStatus, DeviceConfig


logger = logging.getLogger(__name__)

# Confirmed working objects from SEPAC 5.2.0 walk and SNMPv1 probe.
OID_SYS_DESCR = "1.3.6.1.2.1.1.1.0"  # SNMPv2-MIB::sysDescr.0
OID_CURRENT_PATTERN = "1.3.6.1.4.1.1206.2.2.1.1.9.0"
OID_UNIT_STATUS = "1.3.6.1.4.1.1206.2.2.1.1.7.0"
OID_PHASE_STATUS_BASE = "1.3.6.1.4.1.1206.3.3.1.1.1.1.8"
OID_DETECTOR_STATUS_BASE = "1.3.6.1.4.1.1206.3.3.1.2.1.1.1"

# NTCIP 1202 timing/control objects (common scalar controls).
# NOTE: Vendor implementations can vary. Validate on target Siemens M60 docs before production rollout.
OID_SYSTEM_PATTERN_CONTROL = "1.3.6.1.4.1.1206.4.2.1.8.0"
OID_PHASE_CONTROL_HOLD = "1.3.6.1.4.1.1206.4.2.1.9.0"
OID_PHASE_CONTROL_FORCEOFF = "1.3.6.1.4.1.1206.4.2.1.10.0"
OID_PHASE_CONTROL_OMIT = "1.3.6.1.4.1.1206.4.2.1.11.0"


class SiemensM60(Device):
    """Siemens M60 / SEPAC 5.2.0 SNMPv1 polling + legacy command path."""

    def __init__(self, config: DeviceConfig):
        super().__init__(config)
        self._snmp_engine = SnmpEngine()
        self._mp_model = 0  # SNMPv1 is known-good for this controller.

    async def _safe_get_oid(self, target: UdpTransportTarget, oid: str) -> str | None:
        """Read one OID and return value as string or None on timeout/noSuchName."""
        try:
            iterator = get_cmd(
                self._snmp_engine,
                CommunityData(self.config.community, mpModel=self._mp_model),
                target,
                ContextData(),
                ObjectType(ObjectIdentity(oid)),
            )
            error_indication, error_status, _, var_binds = await iterator
            if error_indication or error_status:
                logger.warning(
                    "SiemensM60 GET failed ip=%s oid=%s error=%s",
                    self.config.ip_address,
                    oid,
                    str(error_indication or error_status),
                )
                return None
            return str(var_binds[0][1])
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

    async def connect(self) -> bool:
        """Test connectivity via SNMP."""
        try:
            self.status.errors = []
            target = await UdpTransportTarget.create(
                (self.config.ip_address, self.config.port),
                timeout=self.config.timeout_seconds,
                retries=self.config.retries,
            )
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
        try:
            self.status.errors = []
            target = await UdpTransportTarget.create(
                (self.config.ip_address, self.config.port),
                timeout=self.config.timeout_seconds,
                retries=self.config.retries,
            )

            sys_descr = await self._safe_get_oid(target, OID_SYS_DESCR)
            current_pattern_raw = await self._safe_get_oid(target, OID_CURRENT_PATTERN)
            unit_status_raw = await self._safe_get_oid(target, OID_UNIT_STATUS)

            phase_status: dict[str, int] = {}
            for phase in range(1, 9):
                oid = f"{OID_PHASE_STATUS_BASE}.{phase}"
                phase_status[str(phase)] = self._to_int(await self._safe_get_oid(target, oid)) or 0

            detectors: dict[str, int] = {}
            for detector in range(1, 9):
                oid = f"{OID_DETECTOR_STATUS_BASE}.{detector}"
                detectors[str(detector)] = self._to_int(await self._safe_get_oid(target, oid)) or 0

            current_pattern = self._to_int(current_pattern_raw)
            unit_status_code = self._to_int(unit_status_raw)
            active_phases = [phase for phase, state in phase_status.items() if state > 0]
            active_detectors = [det for det, state in detectors.items() if state > 0]

            self.status.raw_data = {
                "sys_descr": sys_descr or "unavailable",
                "current_pattern": str(current_pattern) if current_pattern is not None else "Unknown",
                "unit_status_code": unit_status_code,
                "unit_status": self._unit_status_text(unit_status_code),
                "phase_status": phase_status,
                "phase_summary": ", ".join(active_phases) if active_phases else "none active",
                "detectors": detectors,
                "detector_summary": ", ".join(active_detectors) if active_detectors else "none active",
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
        target = await UdpTransportTarget.create(
            (self.config.ip_address, self.config.port),
            timeout=self.config.timeout_seconds,
            retries=self.config.retries,
        )
        current_value = await self._safe_get_oid(target, oid)
        probe_ok = current_value is not None
        self.status.raw_data["last_command_probe"] = {
            "label": label,
            "oid": oid,
            "exists": probe_ok,
            "current_value": current_value,
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
            target = await UdpTransportTarget.create(
                (self.config.ip_address, self.config.port),
                timeout=self.config.timeout_seconds,
                retries=self.config.retries,
            )
            iterator = set_cmd(
                self._snmp_engine,
                CommunityData(self.config.community, mpModel=self._mp_model),
                target,
                ContextData(),
                ObjectType(ObjectIdentity(oid), Integer32(int(value))),
            )
            error_indication, error_status, _, _ = await iterator
            if error_indication or error_status:
                logger.warning(
                    "SiemensM60 SET failed ip=%s oid=%s value=%s error=%s",
                    self.config.ip_address,
                    oid,
                    value,
                    str(error_indication or error_status),
                )
                self.status.errors.append(str(error_indication or error_status))
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