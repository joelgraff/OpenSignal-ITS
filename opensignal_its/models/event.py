"""Event and alarm display DTOs for service/UI boundaries."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TimelineDisplayRow(BaseModel):
    timestamp: str = ""
    kind: str = "event"
    kind_label: str = "Event"
    kind_scheme: str = "gray"
    device_ip: str = "unknown"
    summary: str = "Unknown event"
    detail: str = ""
    status_label: str = "Unknown"
    status_scheme: str = "gray"
    raw: str = ""


class AlarmDisplayRow(BaseModel):
    alarm_key: str = ""
    severity: str = "unknown"
    severity_label: str = "Unknown"
    severity_scheme: str = "gray"
    alarm_type: str = "unknown"
    summary: str = "Alarm"
    device_ip: str = "unknown"
    detail: str = ""
    state_label: str = "Active"
    state_scheme: str = "orange"
    state_detail: str = ""
    raw: str = ""


class EventDisplayView(BaseModel):
    timeline: list[TimelineDisplayRow] = Field(default_factory=list)
    alarms: list[AlarmDisplayRow] = Field(default_factory=list)
    acknowledged_alarms: list[AlarmDisplayRow] = Field(default_factory=list)
    silenced_alarms: list[AlarmDisplayRow] = Field(default_factory=list)