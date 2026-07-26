"""Artifact Manager — storage, versioning, retention, signing, metadata."""
import json, uuid, os, logging, hashlib
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class Artifact:
    id: str; org_id: str; name: str; version: str; file_path: str
    size_bytes: int = 0; checksum: str = ""; content_type: str = ""
    repository_id: str = ""; build_id: str = ""; tags: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict); is_signed: bool = False
    retention_days: int = 90; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_at: str = ""

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "Artifact": return cls(**data)

class ArtifactManager:
    def __init__(self, storage_dir: str = "release_data/artifacts"):
        self.storage_dir = storage_dir; self._artifacts: dict[str, Artifact] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "artifacts.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r", encoding="utf-8") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._artifacts[k] = Artifact.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._artifacts.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def register(self, org_id: str, name: str, version: str, file_path: str) -> Artifact:
        checksum = ""
        if os.path.exists(file_path):
            with open(file_path, "rb") as f: checksum = hashlib.sha256(f.read()).hexdigest()
        art = Artifact(id=str(uuid.uuid4()), org_id=org_id, name=name, version=version, file_path=file_path, checksum=checksum)
        art.size_bytes = os.path.getsize(file_path) if os.path.exists(file_path) else 0
        self._artifacts[art.id] = art; self._save(); return art

    def get(self, art_id: str) -> Optional[Artifact]: return self._artifacts.get(art_id)

    def list_by_org(self, org_id: str) -> list[Artifact]:
        return sorted([a for a in self._artifacts.values() if a.org_id == org_id], key=lambda a: a.created_at, reverse=True)

    def get_telemetry(self) -> dict: return dict(self._telemetry)
