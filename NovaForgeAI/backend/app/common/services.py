"""Unified async service layer — wraps all volume modules with config, health, telemetry, error handling."""
import asyncio, logging, time, json
from typing import Optional, Any, TypeVar, Generic, Type
from datetime import datetime, timezone

from .base import Component, HealthRegistry, TelemetryCollector, Config
from .storage import StorageBackend, JsonFileStorage, MemoryStorage

logger = logging.getLogger(__name__)
T = TypeVar("T")


class AsyncService(Component):
    """Base async service with health, telemetry, config, and storage."""

    def __init__(self, name: str, storage: Optional[StorageBackend] = None, config: Optional[Config] = None):
        super().__init__(name)
        self.config = config or Config()
        self.storage = storage or MemoryStorage()
        self.telemetry = TelemetryCollector()
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock(self, key: str) -> asyncio.Lock:
        if key not in self._locks: self._locks[key] = asyncio.Lock()
        return self._locks[key]

    async def safe_call(self, fn, *args, error_msg: str = "Operation failed", **kwargs):
        try:
            self.record_op()
            result = fn(*args, **kwargs)
            if asyncio.iscoroutine(result): result = await result
            return result
        except Exception as e:
            self.record_error()
            logger.error("%s: %s", error_msg, e)
            raise

    def health(self) -> dict:
        h = super().health()
        h["storage_type"] = type(self.storage).__name__
        h["telemetry"] = self.telemetry.snapshot()
        return h


class ServiceRegistry:
    """Global registry of all async services across volumes."""

    def __init__(self):
        self._services: dict[str, AsyncService] = {}
        self.health = HealthRegistry()

    def register(self, service: AsyncService) -> None:
        self._services[service.name] = service
        self.health.register(service.name, service)

    def get(self, name: str) -> Optional[AsyncService]:
        return self._services.get(name)

    def all(self) -> list[AsyncService]:
        return list(self._services.values())

    def health_check(self) -> dict:
        return self.health.check_all()

    def telemetry_snapshot(self) -> dict:
        result = {}
        for name, svc in self._services.items():
            result[name] = svc.telemetry.snapshot()
        return result


# Global service registry instance
registry = ServiceRegistry()
