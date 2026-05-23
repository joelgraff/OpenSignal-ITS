# base.py 
from abc import ABC, abstractmethod
from typing import Any, ClassVar
import asyncio
from ..models.device import DeviceStatus, DeviceConfig


class Device(ABC):
    """Abstract base class for all ITS devices."""

    # Registry of all device types
    _registry: ClassVar[dict[str, type["Device"]]] = {}
    api_version: ClassVar[str] = "1.0"
    device_type: ClassVar[str | None] = None

    def __init__(self, config: DeviceConfig):
        self.config = config
        self.status = DeviceStatus(device_id=config.name or config.ip_address)
        self._polling_task = None

    def __init_subclass__(cls, **kwargs):
        """Auto-register device types."""
        super().__init_subclass__(**kwargs)
        class_key = cls.__name__.lower()
        Device._registry[class_key] = cls
        if cls.device_type:
            Device._registry[cls.device_type.lower()] = cls

    @classmethod
    def create(cls, device_type: str, config: DeviceConfig) -> "Device":
        """Factory method to create devices."""
        if device_type.lower() not in cls._registry:
            raise ValueError(f"Unknown device type: {device_type}")
        return cls._registry[device_type.lower()](config)

    @classmethod
    def registered_types(cls) -> list[str]:
        """List available registry keys."""
        return sorted(cls._registry.keys())

    @classmethod
    def plugin_metadata(cls) -> dict[str, str]:
        """Versioned metadata for plugin discovery and compatibility checks."""
        return {
            "api_version": cls.api_version,
            "device_type": cls.device_type or cls.__name__.lower(),
            "class_name": cls.__name__,
        }

    @abstractmethod
    async def connect(self) -> bool:
        """Establish connection to the device."""
        pass

    @abstractmethod
    async def poll(self) -> DeviceStatus:
        """Poll latest status/data."""
        pass

    @abstractmethod
    async def command(self, command: str, params: dict[str, Any]) -> bool:
        """Send a command (e.g. change timing plan)."""
        pass

    def get_capabilities(self) -> dict[str, Any]:
        """Return device capabilities in a driver-defined schema."""
        return {}

    async def start_polling(self, interval_seconds: int = 5):
        """Background polling."""
        async def poll_loop():
            while True:
                try:
                    self.status = await self.poll()
                except Exception as e:
                    self.status.errors.append(str(e))
                await asyncio.sleep(interval_seconds)
        
        self._polling_task = asyncio.create_task(poll_loop())

    def stop_polling(self):
        if self._polling_task:
            self._polling_task.cancel()