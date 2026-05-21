# siemens_m60.py - Siemens M60 ATC device handler with SNMP and Telnet support.

from pysnmp.hlapi.asyncio import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    get_cmd,
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
        """Example: Change timing plan or manual control."""
        # TODO: Implement SET operations + Telnet fallback
        print(f"[M60 Command] {command} with {params}")
        return True