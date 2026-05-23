"""Shared SNMP client helpers for ITS device drivers."""

from typing import Any

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

from ..models.device import DeviceConfig


class SNMPClient:
    """Thin async SNMP wrapper to keep protocol details out of drivers."""

    def __init__(self, config: DeviceConfig):
        self._config = config
        self._engine = SnmpEngine()

    async def create_target(self) -> UdpTransportTarget:
        return await UdpTransportTarget.create(
            (self._config.ip_address, self._config.port),
            timeout=self._config.timeout_seconds,
            retries=self._config.retries,
        )

    async def get_oid(
        self,
        oid: str,
        mp_model: int,
        target: UdpTransportTarget | None = None,
    ) -> tuple[str | None, str | None]:
        resolved_target = target or await self.create_target()
        iterator = get_cmd(
            self._engine,
            CommunityData(self._config.community, mpModel=mp_model),
            resolved_target,
            ContextData(),
            ObjectType(ObjectIdentity(oid)),
        )
        error_indication, error_status, _, var_binds = await iterator
        if error_indication or error_status:
            return None, str(error_indication or error_status)
        return str(var_binds[0][1]), None

    async def set_int(
        self,
        oid: str,
        value: int,
        mp_model: int,
        target: UdpTransportTarget | None = None,
    ) -> tuple[bool, str | None]:
        resolved_target = target or await self.create_target()
        iterator = set_cmd(
            self._engine,
            CommunityData(self._config.community, mpModel=mp_model),
            resolved_target,
            ContextData(),
            ObjectType(ObjectIdentity(oid), Integer32(int(value))),
        )
        error_indication, error_status, _, _ = await iterator
        if error_indication or error_status:
            return False, str(error_indication or error_status)
        return True, None

    async def probe_oid(
        self,
        oid: str,
        mp_model: int,
        target: UdpTransportTarget | None = None,
    ) -> dict[str, Any]:
        value, error = await self.get_oid(oid, mp_model, target)
        return {
            "exists": value is not None,
            "value": value,
            "error": error,
        }
