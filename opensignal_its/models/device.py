# device.py - Common device models and utilities for OpenSignal ITS

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Dict, Any, Optional


class DeviceStatus(BaseModel):
    """Standardized status for any device."""
    device_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    is_online: bool = False
    status_text: str = "Unknown"
    raw_data: Dict[str, Any] = Field(default_factory=dict)
    extra: Dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)


class DeviceConfig(BaseModel):
    """Basic configuration for any device."""
    ip_address: str
    port: int = 161  # default SNMP
    protocol: str = "snmp"  # snmp, telnet, http, rtsp, etc.
    community: str = "public"  # for SNMPv2c
    snmp_version: str = "auto"  # auto, v2c, v1
    timeout_seconds: float = 3.0
    retries: int = 1
    username: Optional[str] = None
    auth_key: Optional[str] = None
    name: str = "Unnamed Device"
    description: str = ""