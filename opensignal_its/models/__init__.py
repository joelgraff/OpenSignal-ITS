"""Data models for OpenSignal ITS."""

from .fleet import FleetDeviceStatus, FleetRefreshView, FleetSnapshotEntry, RuntimeRegistryView

__all__ = [
	"FleetDeviceStatus",
	"FleetRefreshView",
	"FleetSnapshotEntry",
	"RuntimeRegistryView",
]
