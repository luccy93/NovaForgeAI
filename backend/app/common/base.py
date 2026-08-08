"""Base classes, patterns, registry, config, health checks, metrics, validation for all volumes."""
import json, os, logging, uuid, threading, time
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional, Any, TypeVar, Generic, Callable
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)
T = TypeVar("T")


class Config:
    _instances: dict = {}

    def __init__(self, prefix: str = "NOVAFORGE"):
        self.prefix = prefix; self._values: dict = {}
        self._load()

    def _load(self) -> None:
        for k, v in os.environ.items():
            if k.startswith(self.prefix): self._values[k] = v

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(f"{self.prefix}_{key}", default)

    def get_int(self, key: str, default: int = 0) -> int:
        try: return int(self.get(key, default))
        except: return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        v = self.get(key, str(default)).lower()
        return v in ("true", "1", "yes")


class HealthCheckable(ABC):
    @abstractmethod
    def health(self) -> dict: ...


class Component(HealthCheckable):
    def __init__(self, name: str):
        self.name = name; self._started_at = time.time()
        self._errors: int = 0; self._ops: int = 0

    def record_op(self) -> None: self._ops += 1

    def record_error(self) -> None: self._errors += 1

    def health(self) -> dict:
        return {"name": self.name, "uptime_seconds": time.time() - self._started_at, "operations": self._ops, "errors": self._errors, "status": "healthy" if self._errors < 10 else "degraded"}


class Registry(Generic[T]):
    def __init__(self):
        self._items: dict[str, T] = {}; self._lock = threading.RLock()

    def register(self, key: str, item: T) -> None:
        with self._lock: self._items[key] = item

    def get(self, key: str) -> Optional[T]:
        with self._lock: return self._items.get(key)

    def list(self) -> list[T]:
        with self._lock: return list(self._items.values())

    def count(self) -> int:
        with self._lock: return len(self._items)

    def unregister(self, key: str) -> bool:
        with self._lock:
            if key in self._items: del self._items[key]; return True
            return False


class DataObject:
    id: str; created_at: str; updated_at: str

    def to_dict(self) -> dict:
        d = {}
        for k, v in self.__dict__.items():
            if hasattr(v, "value"): d[k] = v.value
            elif isinstance(v, list): d[k] = [x.to_dict() if hasattr(x, "to_dict") else x for x in v]
            elif isinstance(v, dict): d[k] = {kk: vv.to_dict() if hasattr(vv, "to_dict") else vv for kk, vv in v.items()}
            else: d[k] = v
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "DataObject":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__ if hasattr(cls, "__dataclass_fields__")})


class TelemetryCollector:
    def __init__(self):
        self._metrics: dict[str, int] = {}; self._lock = threading.RLock()

    def increment(self, metric: str, by: int = 1) -> None:
        with self._lock: self._metrics[metric] = self._metrics.get(metric, 0) + by

    def gauge(self, metric: str, value: int) -> None:
        with self._lock: self._metrics[metric] = value

    def snapshot(self) -> dict:
        with self._lock: return dict(self._metrics)

    def reset(self) -> None:
        with self._lock: self._metrics.clear()


class Validator:
    @staticmethod
    def non_empty(value: str, name: str = "value") -> str:
        if not value or not value.strip(): raise ValueError(f"{name} must not be empty")
        return value.strip()

    @staticmethod
    def positive_int(value: int, name: str = "value") -> int:
        if value < 0: raise ValueError(f"{name} must be non-negative, got {value}")
        return value

    @staticmethod
    def in_range(value: float, min_v: float, max_v: float, name: str = "value") -> float:
        if value < min_v or value > max_v: raise ValueError(f"{name} must be between {min_v} and {max_v}, got {value}")
        return value

    @staticmethod
    def valid_uuid(value: str) -> str:
        try: uuid.UUID(value); return value
        except: raise ValueError(f"Invalid UUID: {value}")


class HealthRegistry:
    def __init__(self):
        self._checks: dict[str, HealthCheckable] = {}; self._lock = threading.RLock()

    def register(self, name: str, component: HealthCheckable) -> None:
        with self._lock: self._checks[name] = component

    def check_all(self) -> dict:
        results = {}
        with self._lock:
            for name, component in self._checks.items():
                try: results[name] = component.health()
                except Exception as e: results[name] = {"status": "error", "error": str(e)}
        return results
