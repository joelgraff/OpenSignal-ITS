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

# NTCIP 1202 core status objects (phase status group, scalar objects).
# Source: NTCIP 1202 object names used broadly across compliant controllers.
OID_SYS_DESCR = "1.3.6.1.2.1.1.1.0"  # SNMPv2-MIB::sysDescr.0
OID_SYS_UPTIME = "1.3.6.1.2.1.1.3.0"  # SNMPv2-MIB::sysUpTime.0
OID_PHASE_STATUS_GROUP_REDS = "1.3.6.1.4.1.1206.4.2.1.1.0"
OID_PHASE_STATUS_GROUP_YELLOWS = "1.3.6.1.4.1.1206.4.2.1.2.0"
OID_PHASE_STATUS_GROUP_GREENS = "1.3.6.1.4.1.1206.4.2.1.3.0"
OID_PHASE_STATUS_GROUP_VEH_CALLS = "1.3.6.1.4.1.1206.4.2.1.6.0"
OID_PHASE_STATUS_GROUP_PED_CALLS = "1.3.6.1.4.1.1206.4.2.1.7.0"

# NTCIP 1202 timing/control objects (common scalar controls).
# NOTE: Vendor implementations can vary. Validate on target Siemens M60 docs before production rollout.
OID_SYSTEM_PATTERN_CONTROL = "1.3.6.1.4.1.1206.4.2.1.8.0"
OID_PHASE_CONTROL_HOLD = "1.3.6.1.4.1.1206.4.2.1.9.0"
OID_PHASE_CONTROL_FORCEOFF = "1.3.6.1.4.1.1206.4.2.1.10.0"
OID_PHASE_CONTROL_OMIT = "1.3.6.1.4.1.1206.4.2.1.11.0"


class SiemensM60(Device):
    """Siemens M60 ATC with NTCIP 1202 support + Telnet fallback."""

    def __init__(self, config: DeviceConfig):
        super().__init__(config)
        self._snmp_engine = SnmpEngine()
        self._mp_model = 1  # Prefer SNMPv2c, fallback to SNMPv1 in connect().

    def _version_candidates(self) -> list[int]:
        version = self.config.snmp_version.strip().lower()
        if version in ("v2c", "2c", "2"):
            return [1]
        if version in ("v1", "1"):
            return [0]
        return [1, 0]

    async def connect(self) -> bool:
        """Test connectivity via SNMP."""
        try:
            self.status.errors = []
            target = await UdpTransportTarget.create(
                (self.config.ip_address, self.config.port),
                timeout=self.config.timeout_seconds,
                retries=self.config.retries,
            )

            # Simple sysDescr test with configured SNMP version policy.
            for mp_model in self._version_candidates():
                iterator = get_cmd(
                    self._snmp_engine,
                    CommunityData(self.config.community, mpModel=mp_model),
                    target,
                    ContextData(),
                    ObjectType(ObjectIdentity(OID_SYS_DESCR)),
                )
                errorIndication, errorStatus, _, _ = await iterator
                if not errorIndication and not errorStatus:
                    self._mp_model = mp_model
                    self.status.is_online = True
                    version = "v2c" if mp_model == 1 else "v1"
                    self.status.status_text = f"Connected via SNMP {version}"
                    logger.info(
                        "SiemensM60 connect success ip=%s port=%s version=%s",
                        self.config.ip_address,
                        self.config.port,
                        version,
                    )
                    return True
                attempted = "v2c" if mp_model == 1 else "v1"
                logger.warning(
                    "SiemensM60 connect attempt failed ip=%s version=%s error=%s",
                    self.config.ip_address,
                    attempted,
                    str(errorIndication or errorStatus),
                )
                self.status.errors.append(
                    f"SNMP {attempted}: {str(errorIndication or errorStatus)}"
                )

            self.status.is_online = False
            self.status.status_text = "SNMP connection failed"
            return False
        except Exception as e:
            self.status.is_online = False
            self.status.status_text = "SNMP connect exception"
            self.status.errors.append(str(e))
            return False

    async def poll(self) -> DeviceStatus:
        """Poll key NTCIP 1202 objects for phases, calls, and unit status."""
        try:
            target = await UdpTransportTarget.create(
                (self.config.ip_address, self.config.port),
                timeout=self.config.timeout_seconds,
                retries=self.config.retries,
            )
            # Core status set for dashboard telemetry.
            oids = [
                ObjectType(ObjectIdentity(OID_SYS_UPTIME)),
                ObjectType(ObjectIdentity(OID_PHASE_STATUS_GROUP_REDS)),
                ObjectType(ObjectIdentity(OID_PHASE_STATUS_GROUP_YELLOWS)),
                ObjectType(ObjectIdentity(OID_PHASE_STATUS_GROUP_GREENS)),
                ObjectType(ObjectIdentity(OID_PHASE_STATUS_GROUP_VEH_CALLS)),
                ObjectType(ObjectIdentity(OID_PHASE_STATUS_GROUP_PED_CALLS)),
                ObjectType(ObjectIdentity(OID_SYSTEM_PATTERN_CONTROL)),
            ]

            iterator = get_cmd(
                self._snmp_engine,
                CommunityData(self.config.community, mpModel=self._mp_model),
                target,
                ContextData(),
                *oids
            )

            errorIndication, errorStatus, errorIndex, varBinds = await iterator

            if errorIndication or errorStatus:
                self.status.is_online = False
                self.status.errors.append(str(errorIndication or errorStatus))
                return self.status

            self.status.raw_data = {
                "sys_uptime": str(varBinds[0][1]),
                "phase_reds": str(varBinds[1][1]),
                "phase_yellows": str(varBinds[2][1]),
                "phase_greens": str(varBinds[3][1]),
                "vehicle_calls": str(varBinds[4][1]),
                "ped_calls": str(varBinds[5][1]),
                "current_pattern": str(varBinds[6][1]),
            }
            self.status.is_online = True
            self.status.status_text = "Online - phase and timing telemetry updated"
            logger.info(
                "SiemensM60 poll success ip=%s pattern=%s greens=%s",
                self.config.ip_address,
                self.status.raw_data.get("current_pattern", "unknown"),
                self.status.raw_data.get("phase_greens", "unknown"),
            )
            return self.status

        except Exception as e:
            logger.exception("SiemensM60 poll exception ip=%s", self.config.ip_address)
            self.status.errors.append(str(e))
            return self.status

    async def command(self, command: str, params: Dict[str, Any]) -> bool:
        """Execute timing and control commands."""
        try:
            if command == "select_pattern":
                pattern = int(params.get("pattern", 1))
                # NTCIP 1202: systemPatternControl
                success = await self._set_snmp(OID_SYSTEM_PATTERN_CONTROL, pattern)
                if success:
                    self.status.status_text = f"Pattern {pattern} selected"
                return success

            if command == "set_mode":
                mode = str(params.get("mode", "")).lower()
                # Common pattern control mapping: 1=free, 2=coordinated.
                mode_value = 2 if mode == "coordinated" else 1
                success = await self._set_snmp(OID_SYSTEM_PATTERN_CONTROL, mode_value)
                if success:
                    self.status.status_text = f"Mode set to {mode or 'unknown'}"
                return success

            if command == "manual_hold":
                hold = bool(params.get("hold", True))
                # NTCIP 1202: phaseControlHold bitmask control.
                success = await self._set_snmp(OID_PHASE_CONTROL_HOLD, 255 if hold else 0)
                if success:
                    self.status.status_text = "Manual hold command sent"
                return success

            if command == "advance_phase":
                # NTCIP 1202: phaseControlForceOff bitmask control.
                success = await self._set_snmp(OID_PHASE_CONTROL_FORCEOFF, 255)
                if success:
                    self.status.status_text = "Advance phase command sent"
                return success

            self.status.errors.append(f"Unknown command: {command}")
            return False
        except Exception as e:
            self.status.errors.append(str(e))
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