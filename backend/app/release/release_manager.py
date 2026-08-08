"""Release Manager — release plans, calendar, pipeline, dashboard, notes, changelogs, approval workflows, reports."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class ReleaseStatus(Enum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    READY_FOR_REVIEW = "ready_for_review"
    APPROVED = "approved"
    DEPLOYING = "deploying"
    DEPLOYED = "deployed"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


@dataclass
class Release:
    id: str
    org_id: str
    name: str
    version: str
    status: ReleaseStatus = ReleaseStatus.PLANNED
    channel: str = "stable"
    description: str = ""
    release_notes: str = ""
    changelog: str = ""
    author_id: str = ""
    reviewers: list = field(default_factory=list)
    approvers: list = field(default_factory=list)
    artifacts: list = field(default_factory=list)
    deployments: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    scheduled_at: str = ""
    deployed_at: str = ""
    rolled_back_at: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Release":
        data = data.copy()
        data["status"] = ReleaseStatus(data.get("status", "planned"))
        return cls(**data)


@dataclass
class ReleasePlan:
    id: str
    org_id: str
    name: str
    description: str = ""
    releases: list = field(default_factory=list)
    start_date: str = ""
    end_date: str = ""
    is_active: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "ReleasePlan": return cls(**data)


class ReleaseManager:
    def __init__(self, storage_dir: str = "release_data/releases"):
        self.storage_dir = storage_dir
        self._releases: dict[str, Release] = {}
        self._plans: dict[str, ReleasePlan] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _rel_path(self) -> str: return os.path.join(self.storage_dir, "releases.json")
    def _plan_path(self) -> str: return os.path.join(self.storage_dir, "plans.json")

    def _load(self) -> None:
        for path, store, cls in [
            (self._rel_path(), self._releases, Release),
            (self._plan_path(), self._plans, ReleasePlan),
        ]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = cls.from_dict(v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Failed to load releases: %s", e)

    def _save(self) -> None:
        try:
            with open(self._rel_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._releases.items()}, f, indent=2, default=str)
            with open(self._plan_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._plans.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save releases: %s", e)

    def create_release(self, org_id: str, name: str, version: str, channel: str = "stable", author_id: str = "", description: str = "") -> Release:
        rel = Release(id=str(uuid.uuid4()), org_id=org_id, name=name, version=version, channel=channel, author_id=author_id, description=description)
        self._releases[rel.id] = rel
        self._save()
        return rel

    def get_release(self, rel_id: str) -> Optional[Release]: return self._releases.get(rel_id)

    def update_status(self, rel_id: str, status: ReleaseStatus) -> Optional[Release]:
        rel = self._releases.get(rel_id)
        if not rel: return None
        rel.status = status
        if status == ReleaseStatus.DEPLOYED: rel.deployed_at = datetime.now(timezone.utc).isoformat()
        if status == ReleaseStatus.ROLLED_BACK: rel.rolled_back_at = datetime.now(timezone.utc).isoformat()
        rel.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return rel

    def add_approver(self, rel_id: str, user_id: str) -> bool:
        rel = self._releases.get(rel_id)
        if not rel: return False
        if user_id not in rel.approvers: rel.approvers.append(user_id)
        self._save()
        return True

    def create_plan(self, org_id: str, name: str, description: str = "") -> ReleasePlan:
        plan = ReleasePlan(id=str(uuid.uuid4()), org_id=org_id, name=name, description=description)
        self._plans[plan.id] = plan
        self._save()
        return plan

    def list_releases(self, org_id: str = "", status: Optional[ReleaseStatus] = None, channel: str = "") -> list[Release]:
        results = list(self._releases.values())
        if org_id: results = [r for r in results if r.org_id == org_id]
        if status: results = [r for r in results if r.status == status]
        if channel: results = [r for r in results if r.channel == channel]
        return sorted(results, key=lambda r: r.created_at, reverse=True)

    def get_telemetry(self) -> dict: return dict(self._telemetry)
