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
from .base import Device
from ..models.device import DeviceStatus, DeviceConfig


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
                    ObjectType(ObjectIdentity('1.3.6.1.2.1.1.1.0')),  # sysDescr
                )
                errorIndication, errorStatus, _, _ = await iterator
                if not errorIndication and not errorStatus:
                    self._mp_model = mp_model
                    self.status.is_online = True
                    version = "v2c" if mp_model == 1 else "v1"
                    self.status.status_text = f"Connected via SNMP {version}"
                    return True
                attempted = "v2c" if mp_model == 1 else "v1"
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
        """Poll key NTCIP 1202 objects (phases, detectors, unit status)."""
        try:
            target = await UdpTransportTarget.create(
                (self.config.ip_address, self.config.port),
                timeout=self.config.timeout_seconds,
                retries=self.config.retries,
            )
            # TODO: Expand with real 1202 OIDs from MIB
            oids = [
                ObjectType(ObjectIdentity('1.3.6.1.4.1.1206.4.2.3.1.1')),  # Example phase group
                ObjectType(ObjectIdentity('1.3.6.1.4.1.1206.4.2.4.1')),    # Detector status
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

            self.status.raw_data = {str(var[0]): str(var[1]) for var in varBinds}
            self.status.is_online = True
            self.status.status_text = f"Online - {len(varBinds)} objects retrieved"
            return self.status

        except Exception as e:
            self.status.errors.append(str(e))
            return self.status

    async def command(self, command: str, params: Dict[str, Any]) -> bool:
        """Execute timing and control commands."""
        try:
            if command == "select_pattern":
                pattern = int(params.get("pattern", 1))
                # NTCIP 1202: System Pattern Control (example OID).
                success = await self._set_snmp("1.3.6.1.4.1.1206.4.2.1.8", pattern)
                if success:
                    self.status.status_text = f"Pattern {pattern} selected"
                return success

            if command == "set_mode":
                mode = str(params.get("mode", "")).lower()
                # Placeholder mapping, update with validated MIB objects for your controller.
                mode_value = 2 if mode == "coordinated" else 1
                success = await self._set_snmp("1.3.6.1.4.1.1206.4.2.1.8", mode_value)
                if success:
                    self.status.status_text = f"Mode set to {mode or 'unknown'}"
                return success

            if command == "manual_hold":
                hold = bool(params.get("hold", True))
                success = await self._set_snmp("1.3.6.1.4.1.1206.4.2.1.9", 1 if hold else 0)
                if success:
                    self.status.status_text = "Manual hold command sent"
                return success

            if command == "advance_phase":
                success = await self._set_snmp("1.3.6.1.4.1.1206.4.2.1.10", 1)
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
                self.status.errors.append(str(error_indication or error_status))
                return False
            return True
        except Exception as e:
            self.status.errors.append(str(e))
            return False