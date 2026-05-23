"""Polling orchestration services."""

from ..devices.siemens_m60 import SiemensM60
from ..models.device import DeviceConfig


class PollingService:
    """Collect status snapshots from devices."""

    @staticmethod
    async def collect_siemens_m60_snapshot(config: DeviceConfig) -> tuple[dict, int]:
        device = SiemensM60(config)
        success = await device.connect()
        if success:
            status_payload = (await device.poll()).model_dump(mode="json")
        else:
            status_payload = device.status.model_dump(mode="json")
        mp_model = getattr(device, "_mp_model", 1)
        return status_payload, mp_model
