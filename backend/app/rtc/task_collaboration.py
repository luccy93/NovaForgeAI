"""Task Collaboration — assignments, mentions, checklists, progress, dependencies, milestones."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class CollabTask:
    id: str; org_id: str; title: str; description: str = ""
    assignee_id: str = ""; creator_id: str = ""; priority: str = "medium"
    status: str = "open"; checklist: list = field(default_factory=list)
    dependencies: list = field(default_factory=list); tags: list = field(default_factory=list)
    milestone_id: str = ""; due_date: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "CollabTask": return cls(**data)

@dataclass
class Milestone:
    id: str; org_id: str; name: str; description: str = ""
    target_date: str = ""; tasks: list = field(default_factory=list)
    status: str = "open"; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "Milestone": return cls(**data)

class TaskCollaboration:
    def __init__(self, storage_dir: str = "rtc_data/tasks"):
        self.storage_dir = storage_dir; self._tasks: dict[str, CollabTask] = {}
        self._milestones: dict[str, Milestone] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _task_path(self) -> str: return os.path.join(self.storage_dir, "tasks.json")
    def _mil_path(self) -> str: return os.path.join(self.storage_dir, "milestones.json")

    def _load(self) -> None:
        for path, store, cls in [(self._task_path(), self._tasks, CollabTask), (self._mil_path(), self._milestones, Milestone)]:
            if os.path.exists(path):
                try:
                    with open(path, "r") as f: data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = cls.from_dict(v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._task_path(), "w") as f:
                json.dump({k: v.to_dict() for k, v in self._tasks.items()}, f, indent=2, default=str)
            with open(self._mil_path(), "w") as f:
                json.dump({k: v.to_dict() for k, v in self._milestones.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def create_task(self, org_id: str, title: str, assignee_id: str = "", creator_id: str = "") -> CollabTask:
        t = CollabTask(id=str(uuid.uuid4()), org_id=org_id, title=title, assignee_id=assignee_id, creator_id=creator_id)
        self._tasks[t.id] = t; self._save(); return t

    def update_status(self, task_id: str, status: str) -> Optional[CollabTask]:
        t = self._tasks.get(task_id)
        if not t: return None
        t.status = status; t.updated_at = datetime.now(timezone.utc).isoformat(); self._save(); return t

    def create_milestone(self, org_id: str, name: str) -> Milestone:
        m = Milestone(id=str(uuid.uuid4()), org_id=org_id, name=name)
        self._milestones[m.id] = m; self._save(); return m

    def get_telemetry(self) -> dict: return {"tasks": len(self._tasks), "milestones": len(self._milestones)}
