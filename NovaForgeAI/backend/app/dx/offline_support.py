"""Offline Support — cached documentation, cached search, workspace cache, offline preferences, offline CLI, offline agent memory."""
import json, uuid, os, logging, hashlib
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    id: str
    user_id: str
    cache_key: str
    data: str = ""
    content_type: str = "text"
    size: int = 0
    expires_at: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "CacheEntry": return cls(**data)


class OfflineSupport:
    def __init__(self, storage_dir: str = "dx_data/offline"):
        self.storage_dir = storage_dir
        self._cache: dict[str, CacheEntry] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _store_path(self) -> str: return os.path.join(self.storage_dir, "cache.json")

    def _load(self) -> None:
        path = self._store_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    try: self._cache[k] = CacheEntry.from_dict(v)
                    except Exception as e: logger.warning("Skipping cache %s: %s", k, e)
            except Exception as e: logger.error("Failed to load offline cache: %s", e)

    def _save(self) -> None:
        try:
            with open(self._store_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._cache.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save offline cache: %s", e)

    def cache(self, user_id: str, key: str, data: str, content_type: str = "text", ttl_seconds: int = 3600) -> CacheEntry:
        from datetime import timedelta
        entry = CacheEntry(id=str(uuid.uuid4()), user_id=user_id, cache_key=key, data=data, content_type=content_type, size=len(data.encode()), expires_at=(datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).isoformat())
        self._cache[entry.id] = entry
        self._save()
        return entry

    def get_cached(self, user_id: str, key: str) -> Optional[str]:
        for entry in self._cache.values():
            if entry.user_id == user_id and entry.cache_key == key:
                if entry.expires_at and datetime.fromisoformat(entry.expires_at) > datetime.now(timezone.utc):
                    return entry.data
        return None

    def invalidate(self, user_id: str, key: str = "") -> int:
        count = 0
        to_delete = []
        for eid, entry in self._cache.items():
            if entry.user_id == user_id and (not key or entry.cache_key == key):
                to_delete.append(eid)
                count += 1
        for eid in to_delete: del self._cache[eid]
        if count: self._save()
        return count

    def get_telemetry(self) -> dict: return dict(self._telemetry)
