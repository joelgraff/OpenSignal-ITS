"""Media and RTSP health models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MediaStreamConfig(BaseModel):
    """Configuration for an external media stream."""

    stream_id: str
    name: str = "Unnamed Stream"
    url: str = ""
    timeout_seconds: float = 3.0
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class RtspStreamEndpoint(BaseModel):
    """Normalized RTSP endpoint fields derived from a stream URL."""

    scheme: str = "rtsp"
    host: str
    port: int = 554
    path: str = ""
    query: str = ""
    path_with_query: str = ""
    safe_url: str = ""


class MediaProbeResult(BaseModel):
    """Result returned by a stream health probe."""

    is_online: bool = False
    status_text: str = "Unreachable"
    latency_ms: float | None = None
    errors: list[str] = Field(default_factory=list)
    raw_data: dict[str, Any] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)


class MediaStreamStatus(BaseModel):
    """Sanitized health status for a configured media stream."""

    stream_id: str
    name: str = "Unnamed Stream"
    enabled: bool = True
    is_online: bool = False
    status_text: str = "Unknown"
    checked_at: datetime = Field(default_factory=_utc_now)
    safe_url: str = ""
    latency_ms: float | None = None
    errors: list[str] = Field(default_factory=list)
    raw_data: dict[str, Any] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)