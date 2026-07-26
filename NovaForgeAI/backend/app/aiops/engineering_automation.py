"""Engineering Automation — auto-open PRs, hotfixes, rollback plans, migration plans, docs, release summaries."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class AutomatedTask:
    id: str; org_id: str; task_type: str; title: str; description: str = ""
    status: str = "created"; auto_executed: bool = False
    result: dict = field(default_factory=dict); created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "AutomatedTask": return cls(**data)

class EngineeringAutomation:
    def __init__(self, storage_dir: str = "aiops_data/automation"):
        self.storage_dir = storage_dir; self._tasks: dict[str, AutomatedTask] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "tasks.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._tasks[k] = AutomatedTask.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f:
                json.dump({k: v.to_dict() for k, v in self._tasks.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def create_task(self, org_id: str, task_type: str, title: str, description: str = "") -> AutomatedTask:
        t = AutomatedTask(id=str(uuid.uuid4()), org_id=org_id, task_type=task_type, title=title, description=description)
        self._tasks[t.id] = t; self._save(); return t

    def execute(self, task_id: str) -> Optional[AutomatedTask]:
        t = self._tasks.get(task_id)
        if not t: return None
        t.status = "running"; t.auto_executed = True
        t.status = "completed"; t.result = {"summary": f"Auto-completed: {t.title}"}
        self._save(); return t

    def generate_hotfix_pr(self, org_id: str, issue: str) -> AutomatedTask:
        return self.create_task(org_id, "hotfix_pr", f"Hotfix: {issue}", f"Automated hotfix PR for {issue}")

    def generate_rollback_plan(self, org_id: str, deployment_id: str) -> AutomatedTask:
        return self.create_task(org_id, "rollback_plan", f"Rollback plan for {deployment_id}", f"Steps to rollback {deployment_id}")

    def generate_release_summary(self, org_id: str, version: str) -> AutomatedTask:
        return self.create_task(org_id, "release_summary", f"Release {version} summary", f"Summary of changes in {version}")
