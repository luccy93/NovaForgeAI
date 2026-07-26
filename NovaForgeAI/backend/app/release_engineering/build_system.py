"""Build System — build jobs, stages, caching, dependency resolution, reporting."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)

class BuildStatus(Enum):
    QUEUED = "queued"; RUNNING = "running"; SUCCEEDED = "succeeded"; FAILED = "failed"; CANCELLED = "cancelled"

@dataclass
class Build:
    id: str; org_id: str; repository_id: str; branch: str; commit_sha: str = ""
    status: BuildStatus = BuildStatus.QUEUED; trigger: str = "manual"
    stages: list = field(default_factory=list); artifacts: list = field(default_factory=list)
    duration_seconds: float = 0.0; logs: str = ""
    started_at: str = ""; completed_at: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self); d["status"] = self.status.value; return d
    @classmethod
    def from_dict(cls, data: dict) -> "Build":
        data = data.copy(); data["status"] = BuildStatus(data.get("status", "queued")); return cls(**data)

@dataclass
class BuildCache:
    id: str; org_id: str; key: str; path: str; size_bytes: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_at: str = ""
    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "BuildCache": return cls(**data)

class BuildSystem:
    def __init__(self, storage_dir: str = "release_data/builds"):
        self.storage_dir = storage_dir; self._builds: dict[str, Build] = {}
        self._caches: dict[str, BuildCache] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _build_path(self) -> str: return os.path.join(self.storage_dir, "builds.json")
    def _cache_path(self) -> str: return os.path.join(self.storage_dir, "caches.json")

    def _load(self) -> None:
        for path, store, cls in [(self._build_path(), self._builds, Build), (self._cache_path(), self._caches, BuildCache)]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f: data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = cls.from_dict(v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._build_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._builds.items()}, f, indent=2, default=str)
            with open(self._cache_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._caches.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def queue(self, org_id: str, repo_id: str, branch: str, commit_sha: str = "", trigger: str = "manual") -> Build:
        b = Build(id=str(uuid.uuid4()), org_id=org_id, repository_id=repo_id, branch=branch, commit_sha=commit_sha, trigger=trigger)
        self._builds[b.id] = b; self._save(); return b

    def update_status(self, build_id: str, status: BuildStatus) -> Optional[Build]:
        b = self._builds.get(build_id)
        if not b: return None
        b.status = status
        if status == BuildStatus.RUNNING and not b.started_at: b.started_at = datetime.now(timezone.utc).isoformat()
        if status in (BuildStatus.SUCCEEDED, BuildStatus.FAILED): b.completed_at = datetime.now(timezone.utc).isoformat()
        self._save(); return b

    def cache_put(self, org_id: str, key: str, path: str) -> BuildCache:
        c = BuildCache(id=str(uuid.uuid4()), org_id=org_id, key=key, path=path, size_bytes=os.path.getsize(path) if os.path.exists(path) else 0)
        self._caches[c.id] = c; self._save(); return c

    def cache_get(self, key: str) -> Optional[BuildCache]:
        for c in self._caches.values():
            if c.key == key: return c
        return None
