"""Shared Memory — distributed state, key-value, atomic operations, subscriptions."""
import json, uuid, os, logging, time
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional, Any, Callable

logger = logging.getLogger(__name__)

@dataclass
class SharedMemoryEntry:
    key: str; value: Any; owner_id: str = ""; ttl: int = 0
    version: int = 1; tags: list = field(default_factory=list)
    created_at: float = field(default_factory=time.time); updated_at: float = field(default_factory=time.time)

class SharedMemory:
    def __init__(self):
        self._data: dict[str, SharedMemoryEntry] = {}
        self._watchers: dict[str, list[Callable]] = {}
        self._telemetry: dict = {"entries": 0, "reads": 0, "writes": 0}

    def set(self, key: str, value: Any, owner_id: str = "", ttl: int = 0) -> SharedMemoryEntry:
        entry = self._data.get(key)
        if entry:
            entry.value = value; entry.version += 1; entry.updated_at = time.time()
            if owner_id: entry.owner_id = owner_id
        else:
            entry = SharedMemoryEntry(key=key, value=value, owner_id=owner_id, ttl=ttl)
            self._data[key] = entry; self._telemetry["entries"] += 1
        self._telemetry["writes"] += 1
        self._notify(key, "update", entry)
        return entry

    def get(self, key: str) -> Optional[Any]:
        entry = self._data.get(key)
        if entry:
            self._telemetry["reads"] += 1
            return entry.value
        return None

    def delete(self, key: str) -> bool:
        entry = self._data.pop(key, None)
        if entry: self._telemetry["entries"] -= 1; self._notify(key, "delete", None); return True
        return False

    def watch(self, key: str, callback: Callable) -> None:
        if key not in self._watchers: self._watchers[key] = []
        self._watchers[key].append(callback)

    def _notify(self, key: str, action: str, entry: Optional[SharedMemoryEntry]) -> None:
        for cb in self._watchers.get(key, []):
            try: cb(key, action, entry)
            except Exception as e: logger.error("Watcher error on %s: %s", key, e)

    def get_telemetry(self) -> dict: return dict(self._telemetry)
