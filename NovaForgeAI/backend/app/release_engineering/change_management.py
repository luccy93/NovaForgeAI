"""Change Management — RFCs, change requests, CAB, impact analysis, approvals, audit."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)

class ChangeStatus(Enum):
    DRAFT = "draft"; REVIEW = "review"; APPROVED = "approved"; REJECTED = "rejected"
    IMPLEMENTED = "implemented"; VERIFIED = "verified"; ROLLED_BACK = "rolled_back"

class ChangeCategory(Enum):
    STANDARD = "standard"; NORMAL = "normal"; EMERGENCY = "emergency"; MINOR = "minor"

@dataclass
class ChangeRequest:
    id: str; org_id: str; title: str; description: str = ""
    category: ChangeCategory = ChangeCategory.NORMAL
    status: ChangeStatus = ChangeStatus.DRAFT
    author_id: str = ""; owner_id: str = ""
    risk_level: str = "low"; impact: str = ""; rollback_plan: str = ""
    approvers: list = field(default_factory=list)
    cab_review: bool = False; notes: list = field(default_factory=list)
    implemented_at: str = ""; verified_at: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self); d["category"] = self.category.value; d["status"] = self.status.value; return d
    @classmethod
    def from_dict(cls, data: dict) -> "ChangeRequest":
        data = data.copy(); data["category"] = ChangeCategory(data.get("category", "normal"))
        data["status"] = ChangeStatus(data.get("status", "draft")); return cls(**data)

class ChangeManagement:
    def __init__(self, storage_dir: str = "release_data/changes"):
        self.storage_dir = storage_dir; self._changes: dict[str, ChangeRequest] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "changes.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r", encoding="utf-8") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._changes[k] = ChangeRequest.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._changes.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def create(self, org_id: str, title: str, category: ChangeCategory = ChangeCategory.NORMAL) -> ChangeRequest:
        cr = ChangeRequest(id=str(uuid.uuid4()), org_id=org_id, title=title, category=category)
        self._changes[cr.id] = cr; self._save(); return cr

    def update_status(self, cr_id: str, status: ChangeStatus) -> Optional[ChangeRequest]:
        cr = self._changes.get(cr_id)
        if not cr: return None
        cr.status = status
        if status == ChangeStatus.IMPLEMENTED: cr.implemented_at = datetime.now(timezone.utc).isoformat()
        if status == ChangeStatus.VERIFIED: cr.verified_at = datetime.now(timezone.utc).isoformat()
        cr.updated_at = datetime.now(timezone.utc).isoformat(); self._save(); return cr

    def add_approver(self, cr_id: str, user_id: str) -> bool:
        cr = self._changes.get(cr_id)
        if not cr: return False
        if user_id not in cr.approvers: cr.approvers.append(user_id)
        self._save(); return True
