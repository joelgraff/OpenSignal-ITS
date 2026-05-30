"""GET-only SNMP compatibility probes for traffic signal controllers."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from ..models.device import DeviceConfig
from ..protocols.snmp import SNMPClient


ProbeCallable = Callable[[str, int], Awaitable[tuple[str | None, str | None]]]


PROBE_OID_SPECS: tuple[dict[str, str], ...] = (
    {
        "key": "sys_descr",
        "label": "Standard SNMP sysDescr",
        "oid": "1.3.6.1.2.1.1.1.0",
        "surface": "standard_snmp",
    },
    {
        "key": "m60_current_pattern",
        "label": "M60/SEPAC currentPattern",
        "oid": "1.3.6.1.4.1.1206.2.2.1.1.9.0",
        "surface": "m60_sepac",
    },
    {
        "key": "m60_unit_status",
        "label": "M60/SEPAC unitControlStatus",
        "oid": "1.3.6.1.4.1.1206.2.2.1.1.7.0",
        "surface": "m60_sepac",
    },
    {
        "key": "ntcip_system_pattern_control",
        "label": "NTCIP systemPatternControl",
        "oid": "1.3.6.1.4.1.1206.4.2.1.8.0",
        "surface": "ntcip_1202",
    },
    {
        "key": "ntcip_phase_greens_group_1",
        "label": "NTCIP phaseStatusGroupGreens group 1",
        "oid": "1.3.6.1.4.1.1206.4.2.1.1.4.1.4.1",
        "surface": "ntcip_1202",
    },
    {
        "key": "ntcip_phase_reds_group_1",
        "label": "NTCIP phaseStatusGroupReds group 1",
        "oid": "1.3.6.1.4.1.1206.4.2.1.1.4.1.2.1",
        "surface": "ntcip_1202",
    },
)


class SnmpCompatibilityService:
    """Build a bounded GET-only controller compatibility report."""

    _SNMP_VERSION_MP_MODELS: dict[str, int] = {
        "v1": 0,
        "v2c": 1,
    }

    @staticmethod
    def normalize_versions(raw_versions: list[str] | tuple[str, ...] | None) -> list[str]:
        if not raw_versions:
            return ["v1", "v2c"]

        versions: list[str] = []
        for raw_version in raw_versions:
            normalized = str(raw_version).strip().lower()
            if normalized in {"auto", "all", "both", ""}:
                for version in ("v1", "v2c"):
                    if version not in versions:
                        versions.append(version)
                continue
            if normalized not in SnmpCompatibilityService._SNMP_VERSION_MP_MODELS:
                raise ValueError(f"Unsupported SNMP version for probe: {raw_version}")
            if normalized not in versions:
                versions.append(normalized)

        return versions or ["v1", "v2c"]

    @staticmethod
    async def _default_probe(config: DeviceConfig, oid: str, mp_model: int) -> tuple[str | None, str | None]:
        client = SNMPClient(config)
        target = await client.create_target()
        return await client.get_oid(oid, mp_model, target=target)

    @staticmethod
    def _version_summary(version_result: dict[str, Any]) -> str:
        by_key = {item["key"]: item for item in version_result["objects"]}
        sys_descr_exists = bool(by_key.get("sys_descr", {}).get("exists", False))
        m60_exists = any(
            bool(item.get("exists", False))
            for item in version_result["objects"]
            if item.get("surface") == "m60_sepac"
        )
        ntcip_exists = any(
            bool(item.get("exists", False))
            for item in version_result["objects"]
            if item.get("surface") == "ntcip_1202"
        )

        if not sys_descr_exists and not m60_exists and not ntcip_exists:
            return "No SNMP response even from standard sysDescr; troubleshoot reachability/agent settings before OID compatibility."
        if sys_descr_exists and m60_exists:
            return "Standard SNMP and M60/SEPAC objects responded. Current M60 poller is likely compatible."
        if sys_descr_exists and ntcip_exists:
            return "Standard SNMP and NTCIP objects responded, but M60/SEPAC objects did not. Use a non-M60 OID profile."
        if sys_descr_exists:
            return "Standard SNMP responded, but probed M60/SEPAC and NTCIP status objects did not."
        if ntcip_exists:
            return "NTCIP status objects responded without sysDescr. Check SNMP system group access."
        return "Some M60/SEPAC objects responded without sysDescr. Check SNMP system group access."

    @staticmethod
    def _overall_summary(version_results: list[dict[str, Any]]) -> str:
        if any(result.get("m60_sepac_ready", False) for result in version_results):
            return "At least one SNMP version exposes the M60/SEPAC surface expected by the current poller."
        if any(result.get("ntcip_1202_ready", False) for result in version_results):
            return "Target exposes NTCIP objects but not the M60/SEPAC surface. Build or select a model-specific OID profile."
        if any(result.get("standard_snmp_ready", False) for result in version_results):
            return "Target responds to standard SNMP but not the probed traffic-signal objects. Verify MIB support and permissions."
        return "Target did not respond even to standard SNMP sysDescr. Verify SNMP enablement, version, community, modem/NAT, firewall rules, and UDP/161 reachability before changing OID profiles."

    @staticmethod
    def _recommendation(version_results: list[dict[str, Any]]) -> str:
        m60_versions = [
            str(result["version"])
            for result in version_results
            if result.get("m60_sepac_ready", False)
        ]
        if len(m60_versions) == 1:
            return f"Set the controller profile snmp_version to {m60_versions[0]} for the current M60/SEPAC poller."
        if len(m60_versions) > 1:
            return f"The current M60/SEPAC poller can use SNMP versions: {', '.join(m60_versions)}."

        ntcip_versions = [
            str(result["version"])
            for result in version_results
            if result.get("ntcip_1202_ready", False)
        ]
        if ntcip_versions:
            return "Build or select a model-specific NTCIP profile before using the current M60/SEPAC poller."

        standard_versions = [
            str(result["version"])
            for result in version_results
            if result.get("standard_snmp_ready", False)
        ]
        if standard_versions:
            return "Standard SNMP is reachable, so continue with controller MIB/OID discovery for this model."

        return "Treat this as connectivity or SNMP-agent setup first; an M50-specific OID profile cannot work until basic SNMP responds."

    @staticmethod
    async def probe_controller(
        config: DeviceConfig,
        *,
        versions: list[str] | tuple[str, ...] | None = None,
        probe: ProbeCallable | None = None,
    ) -> dict[str, Any]:
        normalized_versions = SnmpCompatibilityService.normalize_versions(versions)
        version_results: list[dict[str, Any]] = []

        for version in normalized_versions:
            mp_model = SnmpCompatibilityService._SNMP_VERSION_MP_MODELS[version]
            objects: list[dict[str, Any]] = []
            for spec in PROBE_OID_SPECS:
                if probe is None:
                    value, error = await SnmpCompatibilityService._default_probe(config, spec["oid"], mp_model)
                else:
                    value, error = await probe(spec["oid"], mp_model)
                objects.append(
                    {
                        **spec,
                        "exists": value is not None,
                        "value": value if value is not None else "",
                        "error": error or "",
                    }
                )

            standard_snmp_ready = any(
                item["surface"] == "standard_snmp" and item["exists"]
                for item in objects
            )
            m60_sepac_ready = any(
                item["surface"] == "m60_sepac" and item["exists"]
                for item in objects
            )
            ntcip_1202_ready = any(
                item["surface"] == "ntcip_1202" and item["exists"]
                for item in objects
            )
            version_result = {
                "version": version,
                "mp_model": mp_model,
                "standard_snmp_ready": standard_snmp_ready,
                "m60_sepac_ready": m60_sepac_ready,
                "ntcip_1202_ready": ntcip_1202_ready,
                "objects": objects,
            }
            version_result["summary"] = SnmpCompatibilityService._version_summary(version_result)
            version_results.append(version_result)

        return {
            "ip_address": config.ip_address,
            "port": config.port,
            "community": config.community,
            "versions": version_results,
            "summary": SnmpCompatibilityService._overall_summary(version_results),
            "recommendation": SnmpCompatibilityService._recommendation(version_results),
        }