"""Approval Manager — gates, sign-offs, policy enforcement, audit."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)

class ApprovalStatus(Enum):
    PENDING = "pending"; APPROVED = "approved"; REJECTED = "rejected"; SKIPPED = "skipped"

class ApprovalType(Enum):
    MANUAL = "manual"; AUTOMATIC = "automatic"; POLICY = "policy"; COMPLIANCE = "compliance"

@dataclass
class Approval:
    id: str; org_id: str; resource_type: str; resource_id: str  # release, deployment
    status: ApprovalStatus = ApprovalStatus.PENDING; approval_type: ApprovalType = ApprovalType.MANUAL
    required_approvers: int = 1; approvers: list = field(default_factory=list)
    conditions: dict = field(default_factory=dict); notes: str = ""
    approved_by: str = ""; approved_at: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self); d["status"] = self.status.value; d["approval_type"] = self.approval_type.value; return d

    @classmethod
    def from_dict(cls, data: dict) -> "Approval":
        data = data.copy(); data["status"] = ApprovalStatus(data.get("status", "pending"))
        data["approval_type"] = ApprovalType(data.get("approval_type", "manual"))
        return cls(**data)

class ApprovalManager:
    def __init__(self, storage_dir: str = "release_data/approvals"):
        self.storage_dir = storage_dir; self._approvals: dict[str, Approval] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "approvals.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r", encoding="utf-8") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._approvals[k] = Approval.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._approvals.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def create(self, org_id: str, resource_type: str, resource_id: str, approval_type: ApprovalType = ApprovalType.MANUAL, required: int = 1) -> Approval:
        a = Approval(id=str(uuid.uuid4()), org_id=org_id, resource_type=resource_type, resource_id=resource_id, approval_type=approval_type, required_approvers=required)
        self._approvals[a.id] = a; self._save(); return a

    def approve(self, approval_id: str, user_id: str) -> Optional[Approval]:
        a = self._approvals.get(approval_id)
        if not a: return None
        if user_id not in a.approvers: a.approvers.append(user_id)
        if len(a.approvers) >= a.required_approvers:
            a.status = ApprovalStatus.APPROVED; a.approved_by = user_id; a.approved_at = datetime.now(timezone.utc).isoformat()
        self._save(); return a

    def reject(self, approval_id: str, user_id: str, notes: str = "") -> Optional[Approval]:
        a = self._approvals.get(approval_id)
        if not a: return None
        a.status = ApprovalStatus.REJECTED; a.approved_by = user_id; a.notes = notes
        a.approved_at = datetime.now(timezone.utc).isoformat(); self._save(); return a

    def get_telemetry(self) -> dict: return dict(self._telemetry)
