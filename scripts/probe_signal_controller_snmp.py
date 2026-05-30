#!/usr/bin/env python3
"""Probe a traffic signal controller's SNMP/OID compatibility surface."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _ensure_repo_on_path() -> None:
    repo_root = str(_repo_root())
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ip_address", help="Controller or modem IP address to probe.")
    parser.add_argument("--port", type=int, default=161, help="SNMP UDP port. Default: 161")
    parser.add_argument("--community", default="public", help="SNMP community string. Default: public")
    parser.add_argument(
        "--version",
        action="append",
        choices=("v1", "v2c", "auto", "all", "both"),
        default=None,
        help="SNMP version to probe. Repeat for multiple; default probes v1 and v2c.",
    )
    parser.add_argument("--timeout", type=float, default=3.0, help="SNMP timeout seconds. Default: 3")
    parser.add_argument("--retries", type=int, default=1, help="SNMP retries. Default: 1")
    parser.add_argument("--json", action="store_true", help="Print full JSON report instead of compact text.")
    return parser.parse_args()


def _print_text_report(report: dict) -> None:
    print(f"Target: {report['ip_address']}:{report['port']} community={report['community']}")
    print(f"Summary: {report['summary']}")
    recommendation = str(report.get("recommendation", "")).strip()
    if recommendation:
        print(f"Recommendation: {recommendation}")
    print("")
    for version in report["versions"]:
        print(f"SNMP {version['version']} (mpModel={version['mp_model']})")
        print(f"  {version['summary']}")
        for item in version["objects"]:
            state = "OK" if item["exists"] else "MISS"
            detail = item["value"] if item["exists"] else item["error"] or "no value"
            print(f"  [{state}] {item['label']} ({item['oid']}): {detail}")
        print("")


async def _main_async(args: argparse.Namespace) -> int:
    _ensure_repo_on_path()
    from opensignal_its.models.device import DeviceConfig
    from opensignal_its.services import SnmpCompatibilityService

    config = DeviceConfig(
        ip_address=args.ip_address,
        port=args.port,
        community=args.community,
        timeout_seconds=args.timeout,
        retries=args.retries,
        name=f"SNMP probe {args.ip_address}",
    )
    report = await SnmpCompatibilityService.probe_controller(config, versions=args.version)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print_text_report(report)
    return 0


def main() -> int:
    return asyncio.run(_main_async(_parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())