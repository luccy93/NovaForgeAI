import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
import json, uuid, hashlib, time, math
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)


class GovernanceDomain(Enum):
    PROMPT = "prompt"
    MODEL = "model"
    PROVIDER = "provider"
    EMBEDDING = "embedding"
    AGENT = "agent"
    CONTENT = "content"
    COMPLIANCE = "compliance"
    SECURITY = "security"
    COST = "cost"
    USAGE = "usage"


class ApprovalStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes_requested"
    CANCELLED = "cancelled"
    ESCALATED = "escalated"


class PolicyEffect(Enum):
    ALLOW = "allow"
    DENY = "deny"
    WARN = "warn"
    AUDIT = "audit"
    REQUIRE_APPROVAL = "require_approval"


@dataclass
class GovernancePolicy:
    id: str = ""
    name: str = ""
    domain: GovernanceDomain = GovernanceDomain.USAGE
    effect: PolicyEffect = PolicyEffect.ALLOW
    conditions: dict = field(default_factory=dict)
    actions: list[str] = field(default_factory=list)
    resources: list[str] = field(default_factory=list)
    priority: int = 0
    org_id: str = ""
    created_at: str = ""
    updated_at: str = ""
    enabled: bool = True

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now

    def to_dict(self) -> dict:
        d = asdict(self)
        d["domain"] = self.domain.value
        d["effect"] = self.effect.value
        return d

    @staticmethod
    def from_dict(data: dict) -> "GovernancePolicy":
        data = data.copy()
        data["domain"] = GovernanceDomain(data.get("domain", "usage"))
        data["effect"] = PolicyEffect(data.get("effect", "allow"))
        return GovernancePolicy(**data)


@dataclass
class ApprovalRequest:
    id: str = ""
    domain: GovernanceDomain = GovernanceDomain.USAGE
    request_type: str = ""
    requester: str = ""
    target_id: str = ""
    target_version: str = ""
    reason: str = ""
    status: ApprovalStatus = ApprovalStatus.PENDING
    reviewers: list[str] = field(default_factory=list)
    comments: list[dict] = field(default_factory=list)
    created_at: str = ""
    resolved_at: str = ""
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["domain"] = self.domain.value
        d["status"] = self.status.value
        return d

    @staticmethod
    def from_dict(data: dict) -> "ApprovalRequest":
        data = data.copy()
        data["domain"] = GovernanceDomain(data.get("domain", "usage"))
        data["status"] = ApprovalStatus(data.get("status", "pending"))
        return ApprovalRequest(**data)


@dataclass
class ComplianceCheck:
    id: str = ""
    policy_id: str = ""
    target_id: str = ""
    passed: bool = False
    details: dict = field(default_factory=dict)
    score: float = 0.0
    checked_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.checked_at:
            self.checked_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "ComplianceCheck":
        return ComplianceCheck(**data)


@dataclass
class ContentPolicy:
    id: str = ""
    name: str = ""
    rules: list[dict] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    severity: str = "medium"
    enabled: bool = True

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "ContentPolicy":
        return ContentPolicy(**data)


class PolicyManager:
    def __init__(self, storage_dir: str):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._policies_file = self.storage_dir / "governance_policies.json"
        self._compliance_file = self.storage_dir / "compliance_checks.json"
        self._policies: dict[str, GovernancePolicy] = {}
        self._compliance: list[ComplianceCheck] = []
        self._telemetry = defaultdict(int)
        self._load()

    def _save(self):
        try:
            policies_data = {pid: p.to_dict() for pid, p in self._policies.items()}
            self._policies_file.write_text(json.dumps(policies_data, indent=2, default=str))
            compliance_data = [c.to_dict() for c in self._compliance]
            self._compliance_file.write_text(json.dumps(compliance_data, indent=2, default=str))
        except Exception as e:
            logger.error("Failed to save policy data: %s", e, exc_info=True)
            raise

    def _load(self):
        try:
            if self._policies_file.exists():
                data = json.loads(self._policies_file.read_text())
                for pid, pdata in data.items():
                    try:
                        self._policies[pid] = GovernancePolicy.from_dict(pdata)
                    except Exception as e:
                        logger.warning("Skipping malformed policy %s: %s", pid, e)
            if self._compliance_file.exists():
                data = json.loads(self._compliance_file.read_text())
                self._compliance = [ComplianceCheck.from_dict(c) for c in data]
        except Exception as e:
            logger.error("Failed to load policy data: %s", e, exc_info=True)

    def create_policy(self, policy: GovernancePolicy) -> GovernancePolicy:
        self._telemetry["policies_created"] += 1
        if policy.id in self._policies:
            raise ValueError(f"Policy {policy.id} already exists")
        self._policies[policy.id] = policy
        self._save()
        logger.info("Created policy %s: %s (%s, %s)", policy.id, policy.name, policy.domain.value, policy.effect.value)
        return policy

    def get_policy(self, policy_id: str) -> Optional[GovernancePolicy]:
        self._telemetry["get_policy_calls"] += 1
        return self._policies.get(policy_id)

    def update_policy(self, policy_id: str, **updates) -> Optional[GovernancePolicy]:
        self._telemetry["update_policy_calls"] += 1
        policy = self._policies.get(policy_id)
        if not policy:
            logger.warning("Policy %s not found for update", policy_id)
            return None
        for key, val in updates.items():
            if hasattr(policy, key) and key not in ("id", "created_at"):
                if key == "domain":
                    val = GovernanceDomain(val) if isinstance(val, str) else val
                elif key == "effect":
                    val = PolicyEffect(val) if isinstance(val, str) else val
                setattr(policy, key, val)
        policy.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        logger.info("Updated policy %s", policy_id)
        return policy

    def delete_policy(self, policy_id: str) -> bool:
        self._telemetry["policies_deleted"] += 1
        if policy_id in self._policies:
            del self._policies[policy_id]
            self._save()
            logger.info("Deleted policy %s", policy_id)
            return True
        return False

    def evaluate_policy(self, policy_id: str, context: dict) -> dict:
        self._telemetry["evaluate_policy_calls"] += 1
        policy = self._policies.get(policy_id)
        if not policy:
            return {"matched": False, "effect": "deny", "reason": "Policy not found"}
        if not policy.enabled:
            return {"matched": False, "effect": "allow", "reason": "Policy disabled"}

        matched = True
        matched_details = {}
        for cond_key, cond_val in policy.conditions.items():
            context_val = context.get(cond_key)
            if isinstance(cond_val, dict):
                op = cond_val.get("op", "eq")
                expected = cond_val.get("value")
                if op == "eq" and context_val != expected:
                    matched = False
                elif op == "neq" and context_val == expected:
                    matched = False
                elif op == "in" and context_val not in expected:
                    matched = False
                elif op == "contains" and expected not in context_val:
                    matched = False
                elif op == "gt" and not (context_val is not None and context_val > expected):
                    matched = False
                elif op == "lt" and not (context_val is not None and context_val < expected):
                    matched = False
            else:
                if context_val != cond_val:
                    matched = False
            matched_details[cond_key] = {"expected": cond_val, "actual": context_val, "matched": matched}

        return {
            "matched": matched,
            "effect": policy.effect.value if matched else "allow",
            "policy_id": policy.id,
            "policy_name": policy.name,
            "domain": policy.domain.value,
            "priority": policy.priority,
            "details": matched_details,
        }

    def list_policies(self, org_id: Optional[str] = None, enabled_only: bool = False) -> list[GovernancePolicy]:
        self._telemetry["list_policies_calls"] += 1
        results = list(self._policies.values())
        if org_id:
            results = [p for p in results if p.org_id == org_id]
        if enabled_only:
            results = [p for p in results if p.enabled]
        return sorted(results, key=lambda p: p.priority, reverse=True)

    def get_policies_by_domain(self, domain: GovernanceDomain, org_id: Optional[str] = None) -> list[GovernancePolicy]:
        self._telemetry["get_policies_by_domain_calls"] += 1
        results = [p for p in self._policies.values() if p.domain == domain]
        if org_id:
            results = [p for p in results if p.org_id == org_id]
        return sorted(results, key=lambda p: p.priority, reverse=True)

    def check_compliance(self, policy_id: str, target_id: str, context: dict) -> ComplianceCheck:
        self._telemetry["check_compliance_calls"] += 1
        result = self.evaluate_policy(policy_id, context)
        passed = result.get("effect") != "deny"
        check = ComplianceCheck(
            policy_id=policy_id,
            target_id=target_id,
            passed=passed,
            details=result,
            score=100.0 if passed else 0.0,
        )
        self._compliance.append(check)
        self._save()
        logger.info("Compliance check for policy %s on %s: %s", policy_id, target_id, "PASS" if passed else "FAIL")
        return check


class ApprovalWorkflow:
    def __init__(self, storage_dir: str):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._requests_file = self.storage_dir / "approval_requests.json"
        self._requests: dict[str, ApprovalRequest] = {}
        self._telemetry = defaultdict(int)
        self._load()

    def _save(self):
        try:
            data = {rid: r.to_dict() for rid, r in self._requests.items()}
            self._requests_file.write_text(json.dumps(data, indent=2, default=str))
        except Exception as e:
            logger.error("Failed to save approval requests: %s", e, exc_info=True)
            raise

    def _load(self):
        try:
            if self._requests_file.exists():
                data = json.loads(self._requests_file.read_text())
                for rid, rdata in data.items():
                    try:
                        self._requests[rid] = ApprovalRequest.from_dict(rdata)
                    except Exception as e:
                        logger.warning("Skipping malformed approval request %s: %s", rid, e)
        except Exception as e:
            logger.error("Failed to load approval requests: %s", e, exc_info=True)

    def create_request(self, request: ApprovalRequest) -> ApprovalRequest:
        self._telemetry["requests_created"] += 1
        if request.id in self._requests:
            raise ValueError(f"Approval request {request.id} already exists")
        self._requests[request.id] = request
        self._save()
        logger.info("Created approval request %s: %s by %s", request.id, request.request_type, request.requester)
        return request

    def get_request(self, request_id: str) -> Optional[ApprovalRequest]:
        self._telemetry["get_request_calls"] += 1
        return self._requests.get(request_id)

    def approve(self, request_id: str, reviewer: str, comment: str = "") -> Optional[ApprovalRequest]:
        self._telemetry["requests_approved"] += 1
        req = self._requests.get(request_id)
        if not req:
            logger.warning("Approval request %s not found", request_id)
            return None
        if req.status != ApprovalStatus.PENDING:
            raise ValueError(f"Cannot approve request in status {req.status.value}")
        req.status = ApprovalStatus.APPROVED
        req.resolved_at = datetime.now(timezone.utc).isoformat()
        if comment:
            req.comments.append({"author": reviewer, "comment": comment, "timestamp": req.resolved_at})
        self._save()
        logger.info("Request %s approved by %s", request_id, reviewer)
        return req

    def reject(self, request_id: str, reviewer: str, reason: str) -> Optional[ApprovalRequest]:
        self._telemetry["requests_rejected"] += 1
        req = self._requests.get(request_id)
        if not req:
            return None
        if req.status != ApprovalStatus.PENDING:
            raise ValueError(f"Cannot reject request in status {req.status.value}")
        req.status = ApprovalStatus.REJECTED
        req.resolved_at = datetime.now(timezone.utc).isoformat()
        req.comments.append({"author": reviewer, "comment": reason, "timestamp": req.resolved_at})
        self._save()
        logger.info("Request %s rejected by %s: %s", request_id, reviewer, reason)
        return req

    def request_changes(self, request_id: str, reviewer: str, feedback: str) -> Optional[ApprovalRequest]:
        self._telemetry["requests_changes_requested"] += 1
        req = self._requests.get(request_id)
        if not req:
            return None
        if req.status != ApprovalStatus.PENDING:
            raise ValueError(f"Cannot request changes on request in status {req.status.value}")
        req.status = ApprovalStatus.CHANGES_REQUESTED
        req.comments.append({"author": reviewer, "comment": feedback, "timestamp": datetime.now(timezone.utc).isoformat()})
        self._save()
        logger.info("Changes requested on %s by %s", request_id, reviewer)
        return req

    def cancel(self, request_id: str, requester: str) -> Optional[ApprovalRequest]:
        self._telemetry["requests_cancelled"] += 1
        req = self._requests.get(request_id)
        if not req:
            return None
        if req.requester != requester:
            raise ValueError("Only the requester can cancel a request")
        req.status = ApprovalStatus.CANCELLED
        req.resolved_at = datetime.now(timezone.utc).isoformat()
        self._save()
        logger.info("Request %s cancelled by %s", request_id, requester)
        return req

    def escalate(self, request_id: str, escalated_by: str, reason: str) -> Optional[ApprovalRequest]:
        self._telemetry["requests_escalated"] += 1
        req = self._requests.get(request_id)
        if not req:
            return None
        req.status = ApprovalStatus.ESCALATED
        req.comments.append({"author": escalated_by, "comment": f"ESCALATED: {reason}", "timestamp": datetime.now(timezone.utc).isoformat()})
        self._save()
        logger.info("Request %s escalated by %s", request_id, escalated_by)
        return req

    def list_requests(self, status: Optional[ApprovalStatus] = None, domain: Optional[GovernanceDomain] = None) -> list[ApprovalRequest]:
        self._telemetry["list_requests_calls"] += 1
        results = list(self._requests.values())
        if status:
            results = [r for r in results if r.status == status]
        if domain:
            results = [r for r in results if r.domain == domain]
        return sorted(results, key=lambda r: r.created_at, reverse=True)

    def get_my_pending(self, user: str) -> list[ApprovalRequest]:
        self._telemetry["get_my_pending_calls"] += 1
        return [
            r for r in self._requests.values()
            if r.status == ApprovalStatus.PENDING and user in r.reviewers
        ]

    def get_approval_stats(self) -> dict:
        self._telemetry["get_approval_stats_calls"] += 1
        by_status = defaultdict(int)
        by_domain = defaultdict(int)
        total_time = 0.0
        resolved_count = 0
        for r in self._requests.values():
            by_status[r.status.value] += 1
            by_domain[r.domain.value] += 1
            if r.resolved_at and r.created_at:
                try:
                    created = datetime.fromisoformat(r.created_at)
                    resolved = datetime.fromisoformat(r.resolved_at)
                    total_time += (resolved - created).total_seconds()
                    resolved_count += 1
                except (ValueError, TypeError):
                    pass
        avg_resolution_time = round(total_time / resolved_count, 2) if resolved_count > 0 else 0.0
        return {
            "total_requests": len(self._requests),
            "by_status": dict(by_status),
            "by_domain": dict(by_domain),
            "avg_resolution_time_seconds": avg_resolution_time,
            "pending_count": by_status.get("pending", 0),
        }


class ContentModeration:
    def __init__(self, storage_dir: str):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._content_policies_file = self.storage_dir / "content_policies.json"
        self._moderation_results_file = self.storage_dir / "moderation_results.json"
        self._content_policies: dict[str, ContentPolicy] = {}
        self._moderation_results: list[dict] = []
        self._telemetry = defaultdict(int)
        self._load()

    def _save(self):
        try:
            policies_data = {pid: p.to_dict() for pid, p in self._content_policies.items()}
            self._content_policies_file.write_text(json.dumps(policies_data, indent=2, default=str))
            self._moderation_results_file.write_text(json.dumps(self._moderation_results[-1000:], indent=2, default=str))
        except Exception as e:
            logger.error("Failed to save content moderation data: %s", e, exc_info=True)
            raise

    def _load(self):
        try:
            if self._content_policies_file.exists():
                data = json.loads(self._content_policies_file.read_text())
                for pid, pdata in data.items():
                    try:
                        self._content_policies[pid] = ContentPolicy.from_dict(pdata)
                    except Exception as e:
                        logger.warning("Skipping malformed content policy %s: %s", pid, e)
            if self._moderation_results_file.exists():
                self._moderation_results = json.loads(self._moderation_results_file.read_text())
        except Exception as e:
            logger.error("Failed to load content moderation data: %s", e, exc_info=True)

    def check_content(self, content: str, policies: Optional[list[str]] = None) -> dict:
        self._telemetry["content_checks"] += 1
        active_policies = [p for p in self._content_policies.values() if p.enabled]
        if policies:
            active_policies = [p for p in active_policies if p.id in policies]

        results = []
        flagged = False
        for policy in active_policies:
            policy_result = self._apply_single_policy(policy, content)
            if policy_result["flagged"]:
                flagged = True
            results.append(policy_result)

        moderation = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "content_length": len(content),
            "flagged": flagged,
            "policy_results": results,
            "action": "block" if flagged else "allow",
        }
        self._moderation_results.append(moderation)
        self._save()
        return moderation

    def _apply_single_policy(self, policy: ContentPolicy, content: str) -> dict:
        content_lower = content.lower()
        flagged = False
        matched_rules = []

        for rule in policy.rules:
            rule_type = rule.get("type", "keyword")
            rule_value = rule.get("value", "")
            if rule_type == "keyword":
                if rule_value.lower() in content_lower:
                    flagged = True
                    matched_rules.append({"rule": rule, "match": rule_value})
            elif rule_type == "regex":
                import re
                if re.search(rule_value, content, re.IGNORECASE):
                    flagged = True
                    matched_rules.append({"rule": rule, "match": rule_value})
            elif rule_type == "pattern":
                if self._match_pattern(rule_value, content):
                    flagged = True
                    matched_rules.append({"rule": rule, "match": rule_value})
            elif rule_type == "length":
                limit = int(rule.get("limit", 10000))
                if len(content) > limit:
                    flagged = True
                    matched_rules.append({"rule": rule, "match": f"length {len(content)} > {limit}"})

        return {
            "policy_id": policy.id,
            "policy_name": policy.name,
            "severity": policy.severity,
            "flagged": flagged,
            "matched_rules": matched_rules,
            "actions": policy.actions if flagged else [],
        }

    def _match_pattern(self, pattern: str, content: str) -> bool:
        try:
            import re
            return bool(re.search(pattern, content))
        except re.error:
            return False

    def apply_policy(self, policy_id: str, content: str) -> dict:
        self._telemetry["apply_policy_calls"] += 1
        policy = self._content_policies.get(policy_id)
        if not policy:
            return {"error": f"Content policy {policy_id} not found"}
        result = self._apply_single_policy(policy, content)
        moderation = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "content_length": len(content),
            "flagged": result["flagged"],
            "policy_results": [result],
            "action": "block" if result["flagged"] else "allow",
        }
        self._moderation_results.append(moderation)
        self._save()
        return moderation

    def get_moderation_result(self, moderation_id: str) -> Optional[dict]:
        self._telemetry["get_moderation_result_calls"] += 1
        for r in self._moderation_results:
            if r.get("id") == moderation_id:
                return r
        return None

    def list_content_policies(self, enabled_only: bool = False) -> list[ContentPolicy]:
        self._telemetry["list_content_policies_calls"] += 1
        if enabled_only:
            return [p for p in self._content_policies.values() if p.enabled]
        return list(self._content_policies.values())

    def update_content_policy(self, policy_id: str, **updates) -> Optional[ContentPolicy]:
        self._telemetry["update_content_policy_calls"] += 1
        policy = self._content_policies.get(policy_id)
        if not policy:
            logger.warning("Content policy %s not found", policy_id)
            return None
        for key, val in updates.items():
            if hasattr(policy, key) and key != "id":
                setattr(policy, key, val)
        self._save()
        logger.info("Updated content policy %s", policy_id)
        return policy

    def create_content_policy(self, policy: ContentPolicy) -> ContentPolicy:
        self._telemetry["content_policies_created"] += 1
        if policy.id in self._content_policies:
            raise ValueError(f"Content policy {policy.id} already exists")
        self._content_policies[policy.id] = policy
        self._save()
        logger.info("Created content policy %s: %s", policy.id, policy.name)
        return policy


class GovernanceManager(PolicyManager, ApprovalWorkflow, ContentModeration):
    def __init__(self, storage_dir: str):
        PolicyManager.__init__(self, storage_dir)
        ApprovalWorkflow.__init__(self, storage_dir)
        ContentModeration.__init__(self, storage_dir)
        logger.info("GovernanceManager initialized at %s", storage_dir)

    def evaluate_all(self, context: dict, org_id: Optional[str] = None) -> dict:
        self._telemetry["evaluate_all_calls"] += 1
        policies = self.list_policies(org_id=org_id, enabled_only=True)
        results = []
        denied = False
        warnings = []

        for policy in policies:
            result = self.evaluate_policy(policy.id, context)
            results.append(result)
            if result["effect"] == "deny":
                denied = True
            if result["effect"] == "warn":
                warnings.append(result["policy_name"])

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "denied": denied,
            "policies_evaluated": len(results),
            "results": results,
            "warnings": warnings,
            "action": "deny" if denied else "allow",
            "org_id": org_id,
        }

    def get_governance_score(self, org_id: Optional[str] = None) -> dict:
        self._telemetry["get_governance_score_calls"] += 1
        policies = self.list_policies(org_id=org_id)
        total = len(policies)
        enabled = sum(1 for p in policies if p.enabled)
        by_domain = defaultdict(int)
        for p in policies:
            by_domain[p.domain.value] += 1

        approvals = self.get_approval_stats()
        pending_approvals = approvals.get("pending_count", 0)
        total_approvals = approvals.get("total_requests", 0)

        compliance_passed = sum(1 for c in self._compliance if c.passed)
        compliance_total = len(self._compliance)
        compliance_score = round(compliance_passed / compliance_total * 100.0, 2) if compliance_total > 0 else 100.0

        policy_coverage = round(enabled / total * 100.0, 2) if total > 0 else 0.0
        approval_health = round((total_approvals - pending_approvals) / total_approvals * 100.0, 2) if total_approvals > 0 else 100.0

        overall = round((compliance_score * 0.4 + policy_coverage * 0.3 + approval_health * 0.3), 2)

        return {
            "org_id": org_id,
            "overall_score": overall,
            "components": {
                "compliance_score": compliance_score,
                "policy_coverage": policy_coverage,
                "approval_health": approval_health,
            },
            "policies": {
                "total": total,
                "enabled": enabled,
                "by_domain": dict(by_domain),
            },
            "approvals": approvals,
            "status": "healthy" if overall >= 80 else "warning" if overall >= 50 else "critical",
        }

    def generate_audit_report(self, org_id: Optional[str] = None, start: Optional[str] = None, end: Optional[str] = None) -> dict:
        self._telemetry["generate_audit_report_calls"] += 1
        policies = self.list_policies(org_id=org_id)
        approvals = self.list_requests()
        if org_id:
            approvals = [a for a in approvals if a.domain.value in [p.domain.value for p in policies]]

        if start:
            approvals = [a for a in approvals if a.created_at >= start]
        if end:
            approvals = [a for a in approvals if a.created_at <= end]

        compliance_records = self._compliance
        if start:
            compliance_records = [c for c in compliance_records if c.checked_at >= start]
        if end:
            compliance_records = [c for c in compliance_records if c.checked_at <= end]

        by_domain_policies = defaultdict(list)
        for p in policies:
            by_domain_policies[p.domain.value].append(p.name)

        resolved_approvals = [a for a in approvals if a.status in (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED)]
        avg_resolution = 0.0
        if resolved_approvals:
            times = []
            for a in resolved_approvals:
                if a.resolved_at and a.created_at:
                    try:
                        created = datetime.fromisoformat(a.created_at)
                        resolved = datetime.fromisoformat(a.resolved_at)
                        times.append((resolved - created).total_seconds())
                    except (ValueError, TypeError):
                        pass
            if times:
                avg_resolution = sum(times) / len(times)

        return {
            "report_id": str(uuid.uuid4()),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "org_id": org_id,
            "period": {"start": start, "end": end},
            "policies": {
                "total": len(policies),
                "enabled": sum(1 for p in policies if p.enabled),
                "by_domain": {k: len(v) for k, v in by_domain_policies.items()},
            },
            "approvals": {
                "total": len(approvals),
                "resolved": len(resolved_approvals),
                "pending": sum(1 for a in approvals if a.status == ApprovalStatus.PENDING),
                "avg_resolution_time_seconds": round(avg_resolution, 2),
            },
            "compliance": {
                "total_checks": len(compliance_records),
                "passed": sum(1 for c in compliance_records if c.passed),
                "failed": sum(1 for c in compliance_records if not c.passed),
                "pass_rate": round(sum(1 for c in compliance_records if c.passed) / len(compliance_records) * 100.0, 2) if compliance_records else 0.0,
            },
            "governance_score": self.get_governance_score(org_id=org_id),
        }
