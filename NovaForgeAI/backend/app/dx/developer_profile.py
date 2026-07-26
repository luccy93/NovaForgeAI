"""Developer Profile — developer identity, skills, experience, activity summary, and productivity metrics."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class DeveloperProfile:
    id: str
    user_id: str
    org_id: str
    display_name: str = ""
    title: str = ""
    skills: list = field(default_factory=list)
    languages: list = field(default_factory=list)
    frameworks: list = field(default_factory=list)
    repositories: int = 0
    contributions: int = 0
    reviews_completed: int = 0
    deployments: int = 0
    ai_interactions: int = 0
    productivity_score: float = 0.0
    badges: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "DeveloperProfile": return cls(**data)


class DeveloperProfileService:
    def __init__(self, storage_dir: str = "dx_data/profiles"):
        self.storage_dir = storage_dir
        self._profiles: dict[str, DeveloperProfile] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _store_path(self) -> str: return os.path.join(self.storage_dir, "profiles.json")

    def _load(self) -> None:
        path = self._store_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    try: self._profiles[k] = DeveloperProfile.from_dict(v)
                    except Exception as e: logger.warning("Skipping profile %s: %s", k, e)
            except Exception as e: logger.error("Failed to load profiles: %s", e)

    def _save(self) -> None:
        try:
            with open(self._store_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._profiles.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save profiles: %s", e)

    def get_or_create(self, user_id: str, org_id: str) -> DeveloperProfile:
        for p in self._profiles.values():
            if p.user_id == user_id: return p
        prof = DeveloperProfile(id=str(uuid.uuid4()), user_id=user_id, org_id=org_id, display_name=user_id)
        self._profiles[prof.id] = prof
        self._save()
        return prof

    def update(self, user_id: str, updates: dict) -> Optional[DeveloperProfile]:
        for p in self._profiles.values():
            if p.user_id == user_id:
                for k, v in updates.items():
                    if hasattr(p, k) and k not in ("id", "user_id", "created_at"): setattr(p, k, v)
                p.updated_at = datetime.now(timezone.utc).isoformat()
                self._save()
                return p
        return None

    def get_leaderboard(self, org_id: str, metric: str = "productivity_score", top_n: int = 20) -> list[dict]:
        profiles = [p for p in self._profiles.values() if p.org_id == org_id]
        sorted_profiles = sorted(profiles, key=lambda p: getattr(p, metric, 0), reverse=True)
        return [{"rank": i+1, "user_id": p.user_id, metric: getattr(p, metric, 0)} for i, p in enumerate(sorted_profiles[:top_n])]

    def get_telemetry(self) -> dict: return dict(self._telemetry)
