import asyncio
from opensignal_its.models.device import DeviceConfig
from opensignal_its.devices.siemens_m60 import SiemensM60
from pysnmp.hlapi.asyncio import UdpTransportTarget

INTERVAL_SEC = 5
DURATION_SEC = 600


async def get_oid(dev: SiemensM60, target: UdpTransportTarget, oid: str):
    return await dev._safe_get_oid(target, oid)


async def main():
    cfg = DeviceConfig(
        ip_address="166.156.88.223",
        port=161,
        community="public",
        snmp_version="v1",
        timeout_seconds=10,
        retries=2,
        name="oid-change-monitor-long",
    )
    dev = SiemensM60(cfg)
    await dev.connect()
    target = await UdpTransportTarget.create(
        (cfg.ip_address, cfg.port), timeout=cfg.timeout_seconds, retries=cfg.retries
    )

    oids = {
        "sysUpTime": "1.3.6.1.2.1.1.3.0",
        "currentPattern": "1.3.6.1.4.1.1206.2.2.1.1.9.0",
        "unitControlStatus": "1.3.6.1.4.1.1206.2.2.1.1.7.0",
    }
    for p in range(1, 17):
        oids[f"phaseStatus.{p}"] = f"1.3.6.1.4.1.1206.3.3.1.1.1.1.8.{p}"
        oids[f"vehCall.{p}"] = f"1.3.6.1.4.1.1206.3.3.1.1.3.1.2.2.{p}"
        oids[f"pedCall.{p}"] = f"1.3.6.1.4.1.1206.3.3.1.1.3.1.3.2.{p}"
        oids[f"timerVal.{p}"] = f"1.3.6.1.4.1.1206.3.3.1.1.3.1.5.2.{p}"

    samples = max(2, DURATION_SEC // INTERVAL_SEC)
    snapshots = []

    for i in range(samples):
        snap = {}
        for oid in oids.values():
            snap[oid] = await get_oid(dev, target, oid)
        snapshots.append(snap)
        if i < samples - 1:
            await asyncio.sleep(INTERVAL_SEC)

    changed = {}
    for oid in oids.values():
        vals = [s.get(oid) for s in snapshots]
        transitions = sum(1 for i in range(1, len(vals)) if vals[i] != vals[i - 1])
        if transitions > 0:
            changed[oid] = {
                "transitions": transitions,
                "first": vals[0],
                "last": vals[-1],
            }

    print("LONG_MONITOR_RESULT_START")
    print(f"samples={samples} interval_sec={INTERVAL_SEC} duration_sec={DURATION_SEC}")
    for oid, info in sorted(changed.items()):
        print(
            f"{oid} transitions={info['transitions']} first={info['first']} last={info['last']}"
        )
    print(
        f"total_changed={len(changed)} total_monitored={len(oids)} total_unchanged={len(oids) - len(changed)}"
    )
    print("LONG_MONITOR_RESULT_END")


if __name__ == "__main__":
    asyncio.run(main())
