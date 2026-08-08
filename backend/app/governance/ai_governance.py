import json
import uuid
import os
import re
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


class AIGovernanceDomain(Enum):
    PROMPT = "prompt"
    MODEL = "model"
    TOOL = "tool"
    AGENT = "agent"
    PROVIDER = "provider"
    EMBEDDING = "embedding"
    RAG = "rag"
    FINE_TUNING = "fine_tuning"


class ApprovalRequirement(Enum):
    NONE = "none"
    REVIEWER = "reviewer"
    APPROVER = "approver"
    SECURITY_REVIEW = "security_review"
    COMPLIANCE_REVIEW = "compliance_review"
    EXECUTIVE_REVIEW = "executive_review"
    FULL_COMMITTEE = "full_committee"


class ModelRiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class GovernanceAction(Enum):
    ALLOW = "allow"
    BLOCK = "block"
    FLAG = "flag"
    LOG_ONLY = "log_only"
    REQUIRE_JUSTIFICATION = "require_justification"
    REQUIRE_APPROVAL = "require_approval"


@dataclass
class AIGovernancePolicy:
    id: str
    org_id: str
    name: str
    domain: AIGovernanceDomain = AIGovernanceDomain.PROMPT
    model_risk_level: ModelRiskLevel = ModelRiskLevel.MEDIUM
    action: GovernanceAction = GovernanceAction.ALLOW
    approval: ApprovalRequirement = ApprovalRequirement.NONE
    prompt_patterns: list = field(default_factory=list)
    blocked_providers: list = field(default_factory=list)
    blocked_models: list = field(default_factory=list)
    max_tokens_per_request: int = 0
    max_cost_per_request: float = 0.0
    require_audit_log: bool = True
    enabled: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["domain"] = self.domain.value
        d["model_risk_level"] = self.model_risk_level.value
        d["action"] = self.action.value
        d["approval"] = self.approval.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AIGovernancePolicy":
        data["domain"] = AIGovernanceDomain(data["domain"])
        data["model_risk_level"] = ModelRiskLevel(data["model_risk_level"])
        data["action"] = GovernanceAction(data["action"])
        data["approval"] = ApprovalRequirement(data["approval"])
        return cls(**data)


@dataclass
class PromptGovernanceRecord:
    id: str
    org_id: str
    workspace_id: str
    user_id: str
    prompt_text: str = ""
    model: str = ""
    provider: str = ""
    token_count: int = 0
    estimated_cost: float = 0.0
    risk_score: float = 0.0
    action_taken: GovernanceAction = GovernanceAction.ALLOW
    requires_approval: bool = False
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    blocked_reason: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["action_taken"] = self.action_taken.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "PromptGovernanceRecord":
        data["action_taken"] = GovernanceAction(data["action_taken"])
        return cls(**data)


@dataclass
class ModelApprovalRecord:
    id: str
    org_id: str
    model_name: str
    provider: str
    risk_level: ModelRiskLevel = ModelRiskLevel.MEDIUM
    status: str = "pending"
    requested_by: str = ""
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    valid_until: Optional[str] = None
    usage_restrictions: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["risk_level"] = self.risk_level.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ModelApprovalRecord":
        data["risk_level"] = ModelRiskLevel(data["risk_level"])
        return cls(**data)


@dataclass
class AIGovernanceReport:
    id: str
    org_id: str
    period_start: str
    period_end: str
    total_prompts: int = 0
    blocked_prompts: int = 0
    flagged_prompts: int = 0
    total_model_requests: int = 0
    blocked_models: int = 0
    total_cost: float = 0.0
    cost_limit_status: str = "ok"
    policy_violations: list = field(default_factory=list)
    top_violators: list = field(default_factory=list)
    recommendations: list = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AIGovernanceReport":
        return cls(**data)


@dataclass
class AIAuditEntry:
    id: str
    org_id: str
    domain: AIGovernanceDomain
    action: str = ""
    target: str = ""
    actor: str = ""
    details: dict = field(default_factory=dict)
    severity: str = "info"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["domain"] = self.domain.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AIAuditEntry":
        data["domain"] = AIGovernanceDomain(data["domain"])
        return cls(**data)


class AIGovernanceManager:
    def __init__(self, storage_dir: str = "ai_governance_data"):
        self.storage_dir = storage_dir
        self._policies: dict[str, AIGovernancePolicy] = {}
        self._prompt_records: dict[str, PromptGovernanceRecord] = {}
        self._model_approvals: dict[str, ModelApprovalRecord] = {}
        self._audit_entries: dict[str, AIAuditEntry] = {}
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _policies_path(self) -> str:
        return os.path.join(self.storage_dir, "policies.json")

    def _prompt_records_path(self) -> str:
        return os.path.join(self.storage_dir, "prompt_records.json")

    def _model_approvals_path(self) -> str:
        return os.path.join(self.storage_dir, "model_approvals.json")

    def _audit_entries_path(self) -> str:
        return os.path.join(self.storage_dir, "audit_entries.json")

    def _save(self) -> None:
        try:
            policies_data = {pid: p.to_dict() for pid, p in self._policies.items()}
            with open(self._policies_path(), "w", encoding="utf-8") as f:
                json.dump(policies_data, f, indent=2, default=str)

            prompt_data = {rid: r.to_dict() for rid, r in self._prompt_records.items()}
            with open(self._prompt_records_path(), "w", encoding="utf-8") as f:
                json.dump(prompt_data, f, indent=2, default=str)

            model_data = {mid: m.to_dict() for mid, m in self._model_approvals.items()}
            with open(self._model_approvals_path(), "w", encoding="utf-8") as f:
                json.dump(model_data, f, indent=2, default=str)

            audit_data = {eid: e.to_dict() for eid, e in self._audit_entries.items()}
            with open(self._audit_entries_path(), "w", encoding="utf-8") as f:
                json.dump(audit_data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save AI governance data: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._policies_path()):
                with open(self._policies_path(), "r", encoding="utf-8") as f:
                    policies_data = json.load(f)
                for pid, data in policies_data.items():
                    try:
                        self._policies[pid] = AIGovernancePolicy.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed AI governance policy %s: %s", pid, e)

            if os.path.exists(self._prompt_records_path()):
                with open(self._prompt_records_path(), "r", encoding="utf-8") as f:
                    prompt_data = json.load(f)
                for rid, data in prompt_data.items():
                    try:
                        self._prompt_records[rid] = PromptGovernanceRecord.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed prompt record %s: %s", rid, e)

            if os.path.exists(self._model_approvals_path()):
                with open(self._model_approvals_path(), "r", encoding="utf-8") as f:
                    model_data = json.load(f)
                for mid, data in model_data.items():
                    try:
                        self._model_approvals[mid] = ModelApprovalRecord.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed model approval %s: %s", mid, e)

            if os.path.exists(self._audit_entries_path()):
                with open(self._audit_entries_path(), "r", encoding="utf-8") as f:
                    audit_data = json.load(f)
                for eid, data in audit_data.items():
                    try:
                        self._audit_entries[eid] = AIAuditEntry.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed audit entry %s: %s", eid, e)
        except Exception as e:
            logger.error("Failed to load AI governance data: %s", e, exc_info=True)

    def create_governance_policy(self, policy: AIGovernancePolicy) -> AIGovernancePolicy:
        self._telemetry["create_policy_calls"] += 1
        if policy.id in self._policies:
            raise ValueError(f"AI governance policy with id '{policy.id}' already exists.")
        now = datetime.now(timezone.utc).isoformat()
        policy.created_at = now
        policy.updated_at = now
        self._policies[policy.id] = policy
        self._save()
        logger.info("Created AI governance policy: %s (%s)", policy.name, policy.id)
        return policy

    def list_policies(self, org_id: str, domain: Optional[AIGovernanceDomain] = None) -> list[AIGovernancePolicy]:
        self._telemetry["list_policies_calls"] += 1
        results = [p for p in self._policies.values() if p.org_id == org_id]
        if domain:
            results = [p for p in results if p.domain == domain]
        return results

    def evaluate_prompt(self, org_id: str, prompt_text: str, model: str, provider: str, token_count: int, estimated_cost: float) -> dict:
        self._telemetry["evaluate_prompt_calls"] += 1
        policies = self.list_policies(org_id)
        matched_policies = []
        action = GovernanceAction.ALLOW
        blocked_reason = ""
        requires_approval = False
        risk_score = 0.0
        approval_type = ApprovalRequirement.NONE

        for policy in policies:
            if not policy.enabled:
                continue
            if policy.blocked_providers and provider in policy.blocked_providers:
                action = GovernanceAction.BLOCK
                blocked_reason = f"Provider '{provider}' is blocked by policy '{policy.name}'"
                matched_policies.append(policy.id)
                continue
            if policy.blocked_models and model in policy.blocked_models:
                action = GovernanceAction.BLOCK
                blocked_reason = f"Model '{model}' is blocked by policy '{policy.name}'"
                matched_policies.append(policy.id)
                continue
            if policy.max_tokens_per_request > 0 and token_count > policy.max_tokens_per_request:
                action = GovernanceAction.BLOCK
                blocked_reason = f"Token count {token_count} exceeds policy limit of {policy.max_tokens_per_request} (policy '{policy.name}')"
                matched_policies.append(policy.id)
                continue
            if policy.max_cost_per_request > 0 and estimated_cost > policy.max_cost_per_request:
                action = GovernanceAction.BLOCK
                blocked_reason = f"Cost {estimated_cost} exceeds policy limit of {policy.max_cost_per_request} (policy '{policy.name}')"
                matched_policies.append(policy.id)
                continue
            if policy.prompt_patterns:
                for pattern in policy.prompt_patterns:
                    try:
                        if re.search(pattern, prompt_text, re.IGNORECASE):
                            if policy.action == GovernanceAction.BLOCK:
                                action = GovernanceAction.BLOCK
                                blocked_reason = f"Prompt matched blocked pattern '{pattern}' (policy '{policy.name}')"
                            elif policy.action == GovernanceAction.FLAG:
                                action = GovernanceAction.FLAG
                            elif policy.action == GovernanceAction.REQUIRE_APPROVAL:
                                requires_approval = True
                                approval_type = policy.approval
                            elif policy.action == GovernanceAction.LOG_ONLY:
                                if action == GovernanceAction.ALLOW:
                                    action = GovernanceAction.LOG_ONLY
                            elif policy.action == GovernanceAction.REQUIRE_JUSTIFICATION:
                                if action not in (GovernanceAction.BLOCK,):
                                    action = GovernanceAction.REQUIRE_JUSTIFICATION
                            matched_policies.append(policy.id)
                            risk_score += 1.0
                            break
                    except re.error:
                        logger.warning("Invalid regex pattern in policy %s: %s", policy.id, pattern)
                        continue

            if policy.model_risk_level in (ModelRiskLevel.HIGH, ModelRiskLevel.CRITICAL):
                risk_score += 0.5
                if policy.action == GovernanceAction.REQUIRE_APPROVAL:
                    requires_approval = True
                    approval_type = policy.approval

        risk_score = min(risk_score, 10.0)

        return {
            "org_id": org_id,
            "action": action.value,
            "action_taken": action,
            "blocked_reason": blocked_reason,
            "requires_approval": requires_approval,
            "approval_type": approval_type.value,
            "risk_score": risk_score,
            "matched_policies": matched_policies,
        }

    def record_prompt_action(self, record: PromptGovernanceRecord) -> PromptGovernanceRecord:
        self._telemetry["record_prompt_calls"] += 1
        if record.id in self._prompt_records:
            raise ValueError(f"Prompt record with id '{record.id}' already exists.")
        self._prompt_records[record.id] = record
        self._save()
        logger.info("Recorded prompt action: %s (action: %s)", record.id, record.action_taken.value)
        return record

    def approve_model(self, record: ModelApprovalRecord) -> ModelApprovalRecord:
        self._telemetry["approve_model_calls"] += 1
        if record.id in self._model_approvals:
            raise ValueError(f"Model approval record with id '{record.id}' already exists.")
        now = datetime.now(timezone.utc).isoformat()
        record.created_at = now
        self._model_approvals[record.id] = record
        self._save()
        logger.info("Model approval record created: %s (%s/%s)", record.id, record.model_name, record.provider)
        return record

    def check_model_approval(self, model_name: str, provider: str) -> dict:
        self._telemetry["check_model_approval_calls"] += 1
        now = datetime.now(timezone.utc).isoformat()
        for record in self._model_approvals.values():
            if record.model_name == model_name and record.provider == provider:
                if record.valid_until and record.valid_until < now:
                    return {
                        "approved": False,
                        "status": "expired",
                        "record": record.to_dict(),
                        "reason": "Model approval has expired",
                    }
                return {
                    "approved": True,
                    "status": record.status,
                    "record": record.to_dict(),
                    "risk_level": record.risk_level.value,
                    "usage_restrictions": record.usage_restrictions,
                }
        return {
            "approved": False,
            "status": "not_found",
            "reason": f"No approval record found for model '{model_name}' from provider '{provider}'",
        }

    def get_prompt_approval_queue(self, org_id: str) -> list[PromptGovernanceRecord]:
        self._telemetry["get_prompt_approval_queue_calls"] += 1
        return [
            r for r in self._prompt_records.values()
            if r.org_id == org_id and r.requires_approval and r.approved_by is None
        ]

    def approve_prompt(self, record_id: str, approver: str) -> Optional[PromptGovernanceRecord]:
        self._telemetry["approve_prompt_calls"] += 1
        record = self._prompt_records.get(record_id)
        if not record:
            logger.warning("Prompt record %s not found for approval", record_id)
            return None
        if not record.requires_approval:
            logger.warning("Prompt record %s does not require approval", record_id)
            return None
        if record.approved_by is not None:
            logger.warning("Prompt record %s already approved by %s", record_id, record.approved_by)
            return None
        record.approved_by = approver
        record.approved_at = datetime.now(timezone.utc).isoformat()
        record.action_taken = GovernanceAction.ALLOW
        self._save()
        logger.info("Prompt %s approved by %s", record_id, approver)
        return record

    def get_ai_governance_report(self, org_id: str, start_date: str, end_date: str) -> AIGovernanceReport:
        self._telemetry["get_governance_report_calls"] += 1
        total_prompts = 0
        blocked_prompts = 0
        flagged_prompts = 0
        total_cost = 0.0
        policy_violations = []
        top_violators_map: dict[str, int] = defaultdict(int)

        for record in self._prompt_records.values():
            if record.org_id != org_id:
                continue
            if record.timestamp < start_date or record.timestamp > end_date:
                continue
            total_prompts += 1
            total_cost += record.estimated_cost
            if record.action_taken == GovernanceAction.BLOCK:
                blocked_prompts += 1
                if record.blocked_reason:
                    policy_violations.append({
                        "record_id": record.id,
                        "reason": record.blocked_reason,
                        "user_id": record.user_id,
                        "timestamp": record.timestamp,
                    })
                top_violators_map[record.user_id] += 1
            elif record.action_taken == GovernanceAction.FLAG:
                flagged_prompts += 1
                top_violators_map[record.user_id] += 1

        blocked_models = sum(
            1 for r in self._model_approvals.values()
            if r.org_id == org_id and r.status in (
                ApprovalRequirement.SECURITY_REVIEW,
                ApprovalRequirement.COMPLIANCE_REVIEW,
            )
        )

        cost_limit_status = "ok"
        for policy in self._policies.values():
            if policy.org_id == org_id and policy.max_cost_per_request > 0:
                if total_cost > policy.max_cost_per_request * 100:
                    cost_limit_status = "exceeded"
                    break

        top_violators = sorted(top_violators_map.items(), key=lambda x: x[1], reverse=True)[:10]

        recommendations = []
        if blocked_prompts > total_prompts * 0.1:
            recommendations.append("High prompt block rate detected — consider reviewing prompt patterns and policies.")
        if cost_limit_status == "exceeded":
            recommendations.append("Cost limit exceeded — review model usage and apply tighter cost controls.")
        if blocked_models > 0:
            recommendations.append(f"{blocked_models} model(s) have unresolved security or compliance reviews.")

        report = AIGovernanceReport(
            id=str(uuid.uuid4()),
            org_id=org_id,
            period_start=start_date,
            period_end=end_date,
            total_prompts=total_prompts,
            blocked_prompts=blocked_prompts,
            flagged_prompts=flagged_prompts,
            total_model_requests=len(self._model_approvals),
            blocked_models=blocked_models,
            total_cost=round(total_cost, 4),
            cost_limit_status=cost_limit_status,
            policy_violations=policy_violations,
            top_violators=[{"user_id": u, "count": c} for u, c in top_violators],
            recommendations=recommendations,
        )
        self._telemetry["reports_generated"] += 1
        return report

    def log_audit_entry(self, entry: AIAuditEntry) -> AIAuditEntry:
        self._telemetry["log_audit_entry_calls"] += 1
        if entry.id in self._audit_entries:
            raise ValueError(f"Audit entry with id '{entry.id}' already exists.")
        self._audit_entries[entry.id] = entry
        self._save()
        logger.info("Logged AI audit entry: %s (domain: %s, action: %s)", entry.id, entry.domain.value, entry.action)
        return entry

    def get_telemetry(self) -> dict:
        return dict(self._telemetry)
