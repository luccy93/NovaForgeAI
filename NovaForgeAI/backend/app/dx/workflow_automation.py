"""DX Workflow Automation — quick actions, one-click repo import/review/documentation/security scan/test generation/deployment, batch actions for developer workflows."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class QuickActionType(Enum):
    IMPORT_REPO = "import_repo"
    REVIEW_CODE = "review_code"
    GENERATE_DOCS = "generate_docs"
    SECURITY_SCAN = "security_scan"
    GENERATE_TESTS = "generate_tests"
    DEPLOY = "deploy"
    ANALYZE_REPO = "analyze_repo"
    GENERATE_REPORT = "generate_report"


@dataclass
class QuickAction:
    id: str
    user_id: str
    org_id: str
    action_type: QuickActionType
    name: str
    description: str = ""
    config: dict = field(default_factory=dict)
    is_favorite: bool = False
    usage_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["action_type"] = self.action_type.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "QuickAction":
        data = data.copy()
        data["action_type"] = QuickActionType(data.get("action_type", "review_code"))
        return cls(**data)


@dataclass
class BatchAction:
    id: str
    user_id: str
    org_id: str
    actions: list = field(default_factory=list)
    status: str = "pending"
    total: int = 0
    completed: int = 0
    failed: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "BatchAction": return cls(**data)


class DXWorkflowAutomation:
    def __init__(self, storage_dir: str = "dx_data/workflows"):
        self.storage_dir = storage_dir
        self._actions: dict[str, QuickAction] = {}
        self._batches: dict[str, BatchAction] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _act_path(self) -> str: return os.path.join(self.storage_dir, "actions.json")
    def _batch_path(self) -> str: return os.path.join(self.storage_dir, "batches.json")

    def _load(self) -> None:
        for path, store, cls in [
            (self._act_path(), self._actions, QuickAction),
            (self._batch_path(), self._batches, BatchAction),
        ]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = cls.from_dict(v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Failed to load DX workflows: %s", e)

    def _save(self) -> None:
        try:
            with open(self._act_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._actions.items()}, f, indent=2, default=str)
            with open(self._batch_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._batches.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save DX workflows: %s", e)

    def register_action(self, user_id: str, org_id: str, action_type: QuickActionType, name: str, description: str = "", config: dict = None) -> QuickAction:
        act = QuickAction(id=str(uuid.uuid4()), user_id=user_id, org_id=org_id, action_type=action_type, name=name, description=description, config=config or {})
        self._actions[act.id] = act
        self._save()
        return act

    def execute(self, action_id: str) -> dict:
        act = self._actions.get(action_id)
        if not act: return {"error": "Action not found"}
        act.usage_count += 1
        self._save()
        return {"action": act.name, "type": act.action_type.value, "status": "completed", "timestamp": datetime.now(timezone.utc).isoformat()}

    def create_batch(self, user_id: str, org_id: str, actions: list = None) -> BatchAction:
        batch = BatchAction(id=str(uuid.uuid4()), user_id=user_id, org_id=org_id, actions=actions or [], total=len(actions or []))
        self._batches[batch.id] = batch
        self._save()
        return batch

    def list_actions(self, user_id: str = "") -> list[QuickAction]:
        results = list(self._actions.values())
        if user_id: results = [a for a in results if a.user_id == user_id]
        return results

    def get_telemetry(self) -> dict: return dict(self._telemetry)
