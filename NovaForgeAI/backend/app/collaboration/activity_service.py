"""Activity Service — track repository updates, PRs, deployments, security alerts, AI activity, documentation updates, agent activity, workspace/organization events."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class ActivityType(Enum):
    REPOSITORY_UPDATE = "repository_update"
    PULL_REQUEST = "pull_request"
    DEPLOYMENT = "deployment"
    SECURITY_ALERT = "security_alert"
    AI_ACTIVITY = "ai_activity"
    DOCUMENTATION_UPDATE = "documentation_update"
    AGENT_ACTIVITY = "agent_activity"
    WORKSPACE_EVENT = "workspace_event"
    ORGANIZATION_EVENT = "organization_event"
    CODE_REVIEW = "code_review"
    DISCUSSION = "discussion"
    KNOWLEDGE_UPDATE = "knowledge_update"


@dataclass
class Activity:
    id: str
    org_id: str
    user_id: str
    activity_type: ActivityType
    title: str
    description: str = ""
    source: str = ""
    target_id: str = ""
    target_type: str = ""
    metadata: dict = field(default_factory=dict)
    severity: str = "info"
    is_read: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["activity_type"] = self.activity_type.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Activity":
        data = data.copy()
        data["activity_type"] = ActivityType(data.get("activity_type", "workspace_event"))
        return cls(**data)


class ActivityService:
    def __init__(self, storage_dir: str = "collab_data/activities"):
        self.storage_dir = storage_dir
        self._activities: dict[str, Activity] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _store_path(self) -> str: return os.path.join(self.storage_dir, "activities.json")

    def _load(self) -> None:
        path = self._store_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    try: self._activities[k] = Activity.from_dict(v)
                    except Exception as e: logger.warning("Skipping activity %s: %s", k, e)
            except Exception as e: logger.error("Failed to load activities: %s", e)

    def _save(self) -> None:
        try:
            with open(self._store_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._activities.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save activities: %s", e)

    def record(self, org_id: str, user_id: str, activity_type: ActivityType, title: str, description: str = "", source: str = "", target_id: str = "", target_type: str = "", metadata: dict = None, severity: str = "info") -> Activity:
        act = Activity(id=str(uuid.uuid4()), org_id=org_id, user_id=user_id, activity_type=activity_type, title=title, description=description, source=source, target_id=target_id, target_type=target_type, metadata=metadata or {}, severity=severity)
        self._activities[act.id] = act
        self._save()
        return act

    def get_feed(self, org_id: str = "", user_id: str = "", activity_type: Optional[ActivityType] = None, limit: int = 50) -> list[Activity]:
        results = list(self._activities.values())
        if org_id: results = [a for a in results if a.org_id == org_id]
        if user_id: results = [a for a in results if a.user_id == user_id]
        if activity_type: results = [a for a in results if a.activity_type == activity_type]
        return sorted(results, key=lambda a: a.created_at, reverse=True)[:limit]

    def mark_read(self, activity_id: str) -> bool:
        act = self._activities.get(activity_id)
        if not act: return False
        act.is_read = True
        self._save()
        return True

    def mark_all_read(self, org_id: str, user_id: str) -> int:
        count = 0
        for act in self._activities.values():
            if act.org_id == org_id and act.user_id == user_id and not act.is_read:
                act.is_read = True
                count += 1
        if count: self._save()
        return count

    def get_unread_count(self, org_id: str, user_id: str) -> int:
        return sum(1 for a in self._activities.values() if a.org_id == org_id and a.user_id == user_id and not a.is_read)

    def get_telemetry(self) -> dict: return dict(self._telemetry)
