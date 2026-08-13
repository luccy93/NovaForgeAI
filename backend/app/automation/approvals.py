"""Human approval workflow (Volume 33).

Steps that (a) declare needs_approval, (b) are high-risk per policy, or
(c) touch protected actions require an approval record before the engine
may execute them. Approvals are persisted, tenant-scoped, with actor,
decision, reason and expiry.
"""
import logging, time
from dataclasses import dataclass, field
from typing import Any, Optional

from ..common.storage import JsonFileStorage

logger = logging.getLogger(__name__)

APPROVAL_STATUSES = ("pending", "approved", "rejected", "expired", "auto_approved")
DECISION_ACTORS = ("human", "policy", "ai")


@dataclass
class ApprovalRequest:
    workflow_id: str
    step_id: str
    organization_id: str = ""
    decision: str = "pending"
    actor: str = ""
    actor_type: str = "human"
    reason: str = ""
    created_at: str = field(default_factory=lambda: time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    expires_at: Optional[str] = None
    execution_id: str = ""

    def to_dict(self) -> dict:
        return self.__dict__


class ApprovalStore:
    def __init__(self, storage: Optional[JsonFileStorage] = None):
        self._storage = storage or JsonFileStorage(
            "data/automation/approvals.json")

    def create(self, workflow_id: str, step_id: str,
               organization_id: str = "", execution_id: str = "",
               ttl_s: int | None = None) -> ApprovalRequest:
        req = ApprovalRequest(
            workflow_id=workflow_id, step_id=step_id,
            organization_id=organization_id, execution_id=execution_id)
        if ttl_s is not None:
            req.expires_at = time.strftime(
                "%Y-%m-%dT%H:%M:%SZ",
                time.gmtime(time.time() + ttl_s))
        self._storage.set(request_key(workflow_id, step_id, organization_id),
                          req.to_dict())
        return req

    def get(self, workflow_id: str, step_id: str,
            organization_id: str = "") -> Optional[ApprovalRequest]:
        raw = self._storage.get(request_key(workflow_id, step_id, organization_id))
        return ApprovalRequest(**raw) if raw else None

    def decide(self, workflow_id: str, step_id: str, decision: str,
               actor: str, reason: str = "", actor_type: str = "human",
               organization_id: str = "") -> Optional[ApprovalRequest]:
        assert decision in APPROVAL_STATUSES, f"bad decision {decision}"
        req = self.get(workflow_id, step_id, organization_id)
        if req is None:
            return None
        if req.decision != "pending":
            raise ValueError(
                f"approval for {workflow_id}/{step_id} already decided "
                f"({req.decision})")
        req.decision = decision
        req.actor = actor
        req.actor_type = actor_type
        req.reason = reason
        if decision in ("auto_approved", "approved"):
            req.expires_at = None  # a fresh decision supersedes expiry
        self._storage.set(request_key(workflow_id, step_id, organization_id),
                          req.to_dict())
        return req

    def auto_approve(self, workflow_id: str, step_id: str,
                     organization_id: str = "",
                     policy: str = "") -> Optional[ApprovalRequest]:
        return self.decide(workflow_id, step_id, "auto_approved",
                           actor=policy or "policy_engine",
                           actor_type="policy",
                           reason="policy auto-approval",
                           organization_id=organization_id)

    def is_expired(self, req: ApprovalRequest) -> bool:
        if not req.expires_at:
            return False
        expires = time.strptime(req.expires_at, "%Y-%m-%dT%H:%M:%SZ")
        return time.mktime(expires) < time.time()

    def pending_count(self) -> int:
        return sum(1 for v in self._storage.get_all().values()
                   if v.get("decision") == "pending")

    def count(self) -> int:
        return len(self._storage.get_all())

    def needs_decision(self, workflow_id: str, step_id: str,
                       organization_id: str = "") -> bool:
        req = self.get(workflow_id, step_id, organization_id)
        if req is None:
            return True
        if self.is_expired(req):
            return True
        return req.decision != "approved" and req.decision != "auto_approved"


def request_key(workflow_id: str, step_id: str, organization_id: str) -> str:
    tenant = organization_id or "default"
    return f"{tenant}:{workflow_id}:{step_id}"