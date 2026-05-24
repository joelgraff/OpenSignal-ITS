"""Fleet refresh DTOs used by service and state orchestration."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class FleetDeviceStatus(BaseModel):
    device_type: str
    is_online: bool = False
    status_text: str = "unknown"
    timestamp: str = ""


class FleetSnapshotEntry(BaseModel):
    device_id: str
    device_type: str
    status: FleetDeviceStatus
    row: str
    payload: dict[str, Any] | None = None
    mp_model: int = 1


class FleetRefreshView(BaseModel):
    rows: list[str] = Field(default_factory=list)
    status_by_id: dict[str, FleetDeviceStatus] = Field(default_factory=dict)
    selected_payload: dict[str, Any] | None = None
    selected_mp_model: int = 1
    selected_device_type: str = "siemens_m60"
    selected_device_id: str = ""


class RuntimeRegistryView(BaseModel):
    summary: str = "Runtime registry idle."
    rows: list[str] = Field(default_factory=list)
    count: int = 0
    running_count: int = 0
