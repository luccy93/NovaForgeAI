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


class PolicyType(Enum):
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    REPOSITORY = "repository"
    DEPLOYMENT = "deployment"
    SECURITY = "security"
    AI_USAGE = "ai_usage"
    PROMPT = "prompt"
    LLM_PROVIDER = "llm_provider"
    PLUGIN = "plugin"
    EXTENSION = "extension"
    WORKSPACE = "workspace"
    ORGANIZATION = "organization"
    BILLING = "billing"
    DATA_RETENTION = "data_retention"
    COMPLIANCE = "compliance"
    AI_MODEL = "ai_model"
    AI_PROMPT = "ai_prompt"
    AI_AGENT = "ai_agent"
    AI_TOOL = "ai_tool"
    AI_POLICY = "ai_policy"


class PolicyEffect(Enum):
    ALLOW = "allow"
    DENY = "deny"
    WARN = "warn"
    REQUIRE_APPROVAL = "require_approval"
    ESCALATE = "escalate"
    RETRY = "retry"
    ROLLBACK = "rollback"
    CUSTOM = "custom"


class PolicyStatus(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    DEPRECATED = "deprecated"
    SUNSET = "sunset"
    ERROR = "error"


class PolicySeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ConstraintOperator(Enum):
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    MATCHES = "matches"
    EXISTS = "exists"
    NOT_EXISTS = "not_exists"


@dataclass
class PolicyConstraint:
    field: str
    operator: ConstraintOperator
    value: Any = None
    description: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["operator"] = self.operator.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "PolicyConstraint":
        data["operator"] = ConstraintOperator(data["operator"])
        return cls(**data)


@dataclass
class PolicyAction:
    action_type: str
    params: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PolicyAction":
        return cls(**data)


@dataclass
class Policy:
    id: str
    org_id: str
    name: str
    description: str = ""
    type: PolicyType = PolicyType.SECURITY
    effect: PolicyEffect = PolicyEffect.DENY
    severity: PolicySeverity = PolicySeverity.MEDIUM
    constraints: list[PolicyConstraint] = field(default_factory=list)
    actions: list[PolicyAction] = field(default_factory=list)
    priority: int = 0
    tags: list[str] = field(default_factory=list)
    version: str = "1.0.0"
    status: PolicyStatus = PolicyStatus.DRAFT
    created_by: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    deprecated_at: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["type"] = self.type.value
        d["effect"] = self.effect.value
        d["status"] = self.status.value
        d["severity"] = self.severity.value
        d["constraints"] = [c.to_dict() for c in self.constraints]
        d["actions"] = [a.to_dict() for a in self.actions]
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Policy":
        data["type"] = PolicyType(data["type"])
        data["effect"] = PolicyEffect(data["effect"])
        data["status"] = PolicyStatus(data["status"])
        data["severity"] = PolicySeverity(data["severity"])
        data["constraints"] = [PolicyConstraint.from_dict(c) for c in data["constraints"]]
        data["actions"] = [PolicyAction.from_dict(a) for a in data["actions"]]
        return cls(**data)


@dataclass
class PolicyVersion:
    id: str
    policy_id: str
    version: str
    changes: str = ""
    snapshot: dict = field(default_factory=dict)
    created_by: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PolicyVersion":
        return cls(**data)


@dataclass
class PolicyEvaluationResult:
    id: str
    policy_id: str
    policy_name: str
    type: PolicyType
    effect: PolicyEffect
    matched: bool = False
    decision: str = ""
    score: float = 0.0
    constraints_evaluated: int = 0
    constraints_passed: int = 0
    details: list = field(default_factory=list)
    evaluated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["type"] = self.type.value
        d["effect"] = self.effect.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "PolicyEvaluationResult":
        data["type"] = PolicyType(data["type"])
        data["effect"] = PolicyEffect(data["effect"])
        return cls(**data)


@dataclass
class PolicySimulationResult:
    id: str
    org_id: str
    scenario_name: str
    policies_evaluated: int = 0
    total_passed: int = 0
    total_failed: int = 0
    total_warnings: int = 0
    results: list[PolicyEvaluationResult] = field(default_factory=list)
    recommendations: list = field(default_factory=list)
    simulated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["results"] = [r.to_dict() for r in self.results]
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "PolicySimulationResult":
        data["results"] = [PolicyEvaluationResult.from_dict(r) for r in data["results"]]
        return cls(**data)


@dataclass
class PolicyAuditEntry:
    id: str
    org_id: str
    policy_id: str
    action: str
    changes: dict = field(default_factory=dict)
    performed_by: str = ""
    performed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PolicyAuditEntry":
        return cls(**data)


class PolicyEngine:
    def __init__(self, storage_dir: str = "policy_engine_data"):
        self.storage_dir = storage_dir
        self._policies: dict[str, Policy] = {}
        self._versions: dict[str, list[PolicyVersion]] = defaultdict(list)
        self._audit_log: list[PolicyAuditEntry] = []
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _policies_path(self) -> str:
        return os.path.join(self.storage_dir, "policies.json")

    def _versions_path(self) -> str:
        return os.path.join(self.storage_dir, "versions.json")

    def _audit_path(self) -> str:
        return os.path.join(self.storage_dir, "audit.json")

    def _save(self) -> None:
        try:
            policies_data = {pid: p.to_dict() for pid, p in self._policies.items()}
            with open(self._policies_path(), "w", encoding="utf-8") as f:
                json.dump(policies_data, f, indent=2, default=str)

            versions_data = {pid: [v.to_dict() for v in vlist] for pid, vlist in self._versions.items()}
            with open(self._versions_path(), "w", encoding="utf-8") as f:
                json.dump(versions_data, f, indent=2, default=str)

            audit_data = [e.to_dict() for e in self._audit_log]
            with open(self._audit_path(), "w", encoding="utf-8") as f:
                json.dump(audit_data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save policy engine data: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._policies_path()):
                with open(self._policies_path(), "r", encoding="utf-8") as f:
                    policies_data = json.load(f)
                for pid, data in policies_data.items():
                    try:
                        self._policies[pid] = Policy.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed policy %s: %s", pid, e)

            if os.path.exists(self._versions_path()):
                with open(self._versions_path(), "r", encoding="utf-8") as f:
                    versions_data = json.load(f)
                for pid, vlist in versions_data.items():
                    self._versions[pid] = []
                    for vdata in vlist:
                        try:
                            self._versions[pid].append(PolicyVersion.from_dict(vdata))
                        except Exception as e:
                            logger.warning("Skipping malformed version for policy %s: %s", pid, e)

            if os.path.exists(self._audit_path()):
                with open(self._audit_path(), "r", encoding="utf-8") as f:
                    audit_data = json.load(f)
                for edata in audit_data:
                    try:
                        self._audit_log.append(PolicyAuditEntry.from_dict(edata))
                    except Exception as e:
                        logger.warning("Skipping malformed audit entry: %s", e)
        except Exception as e:
            logger.error("Failed to load policy engine data: %s", e, exc_info=True)

    def _audit(self, org_id: str, policy_id: str, action: str, changes: dict, performed_by: str) -> None:
        entry = PolicyAuditEntry(
            id=str(uuid.uuid4()),
            org_id=org_id,
            policy_id=policy_id,
            action=action,
            changes=changes,
            performed_by=performed_by,
        )
        self._audit_log.append(entry)
        self._telemetry["audit_entries"] += 1

    def create_policy(self, policy: Policy) -> Policy:
        self._telemetry["create_policy_calls"] += 1
        if policy.id in self._policies:
            raise ValueError(f"Policy with id '{policy.id}' already exists.")
        now = datetime.now(timezone.utc).isoformat()
        policy.created_at = now
        policy.updated_at = now
        self._policies[policy.id] = policy

        version_entry = PolicyVersion(
            id=str(uuid.uuid4()),
            policy_id=policy.id,
            version=policy.version,
            changes="Initial creation",
            snapshot=policy.to_dict(),
            created_by=policy.created_by,
        )
        self._versions[policy.id].append(version_entry)
        self._audit(policy.org_id, policy.id, "created", {"version": policy.version}, policy.created_by)
        self._save()
        logger.info("Created policy: %s (%s)", policy.name, policy.id)
        return policy

    def get_policy(self, policy_id: str) -> Optional[Policy]:
        self._telemetry["get_policy_calls"] += 1
        return self._policies.get(policy_id)

    def update_policy(self, policy_id: str, updates: dict) -> Optional[Policy]:
        self._telemetry["update_policy_calls"] += 1
        policy = self._policies.get(policy_id)
        if not policy:
            logger.warning("Attempted to update unknown policy: %s", policy_id)
            return None
        changes = {}
        for key, value in updates.items():
            if hasattr(policy, key) and key not in ("id", "created_at"):
                old_val = getattr(policy, key)
                if key == "type":
                    setattr(policy, key, PolicyType(value) if isinstance(value, str) else value)
                elif key == "effect":
                    setattr(policy, key, PolicyEffect(value) if isinstance(value, str) else value)
                elif key == "status":
                    setattr(policy, key, PolicyStatus(value) if isinstance(value, str) else value)
                elif key == "severity":
                    setattr(policy, key, PolicySeverity(value) if isinstance(value, str) else value)
                elif key == "constraints":
                    setattr(policy, key, [PolicyConstraint.from_dict(c) if isinstance(c, dict) else c for c in value])
                elif key == "actions":
                    setattr(policy, key, [PolicyAction.from_dict(a) if isinstance(a, dict) else a for a in value])
                else:
                    setattr(policy, key, value)
                changes[key] = {"old": str(old_val) if not isinstance(old_val, (list, dict)) else old_val, "new": str(value) if not isinstance(value, (list, dict)) else value}
        policy.updated_at = datetime.now(timezone.utc).isoformat()
        self._audit(policy.org_id, policy_id, "updated", changes, updates.get("created_by", ""))
        self._save()
        logger.info("Updated policy: %s", policy_id)
        return policy

    def delete_policy(self, policy_id: str) -> bool:
        self._telemetry["delete_policy_calls"] += 1
        policy = self._policies.get(policy_id)
        if not policy:
            return False
        policy.status = PolicyStatus.DEPRECATED
        policy.deprecated_at = datetime.now(timezone.utc).isoformat()
        policy.updated_at = policy.deprecated_at
        self._audit(policy.org_id, policy_id, "deleted", {"status": "deprecated"}, "")
        self._save()
        logger.info("Soft-deleted (deprecated) policy: %s", policy_id)
        return True

    def list_policies(self, org_id: Optional[str] = None, type: Optional[PolicyType] = None, status: Optional[PolicyStatus] = None) -> list[Policy]:
        self._telemetry["list_policies_calls"] += 1
        results = list(self._policies.values())
        if org_id:
            results = [p for p in results if p.org_id == org_id]
        if type:
            results = [p for p in results if p.type == type]
        if status:
            results = [p for p in results if p.status == status]
        return results

    def search_policies(self, query: str) -> list[Policy]:
        self._telemetry["search_policies_calls"] += 1
        q = query.lower()
        results = []
        for policy in self._policies.values():
            if (q in policy.name.lower() or q in policy.description.lower() or
                q in policy.id.lower() or q in policy.org_id.lower() or
                any(q in t.lower() for t in policy.tags)):
                results.append(policy)
        return results

    def create_policy_version(self, policy_id: str, created_by: str = "") -> Optional[PolicyVersion]:
        self._telemetry["create_policy_version_calls"] += 1
        policy = self._policies.get(policy_id)
        if not policy:
            logger.warning("Attempted to version unknown policy: %s", policy_id)
            return None
        existing = self._versions.get(policy_id, [])
        major, minor, patch = policy.version.split(".")
        new_version = f"{major}.{minor}.{int(patch) + 1}"
        version_entry = PolicyVersion(
            id=str(uuid.uuid4()),
            policy_id=policy_id,
            version=new_version,
            changes=f"Auto-version bump to {new_version}",
            snapshot=policy.to_dict(),
            created_by=created_by,
        )
        self._versions[policy_id].append(version_entry)
        policy.version = new_version
        policy.updated_at = datetime.now(timezone.utc).isoformat()
        self._audit(policy.org_id, policy_id, "version_created", {"new_version": new_version}, created_by)
        self._save()
        logger.info("Created version %s for policy %s", new_version, policy_id)
        return version_entry

    def get_policy_versions(self, policy_id: str) -> list[PolicyVersion]:
        self._telemetry["get_policy_versions_calls"] += 1
        return list(self._versions.get(policy_id, []))

    def rollback_policy(self, policy_id: str, version_id: str) -> Optional[Policy]:
        self._telemetry["rollback_policy_calls"] += 1
        policy = self._policies.get(policy_id)
        if not policy:
            return None
        versions = self._versions.get(policy_id, [])
        target = next((v for v in versions if v.id == version_id), None)
        if not target:
            logger.warning("Version %s not found for policy %s", version_id, policy_id)
            return None
        restored = Policy.from_dict(target.snapshot)
        restored.id = policy_id
        restored.updated_at = datetime.now(timezone.utc).isoformat()
        self._policies[policy_id] = restored

        new_version = PolicyVersion(
            id=str(uuid.uuid4()),
            policy_id=policy_id,
            version=restored.version,
            changes=f"Rolled back to version {target.version}",
            snapshot=restored.to_dict(),
            created_by="",
        )
        self._versions[policy_id].append(new_version)
        self._audit(policy.org_id, policy_id, "rollback", {"rolled_back_to_version": target.version}, "")
        self._save()
        logger.info("Rolled back policy %s to version %s", policy_id, target.version)
        return restored

    def evaluate_policy(self, policy: Policy, context: dict) -> PolicyEvaluationResult:
        self._telemetry["evaluate_policy_calls"] += 1
        result_id = str(uuid.uuid4())
        details = []
        constraints_evaluated = len(policy.constraints)
        constraints_passed = 0

        for constraint in policy.constraints:
            detail = {
                "field": constraint.field,
                "operator": constraint.operator.value,
                "expected": constraint.value,
                "actual": None,
                "passed": False,
                "description": constraint.description,
            }
            actual_value = self._resolve_field(context, constraint.field)
            detail["actual"] = actual_value

            if self._evaluate_constraint(constraint.operator, actual_value, constraint.value):
                constraints_passed += 1
                detail["passed"] = True

            details.append(detail)

        all_passed = constraints_passed == constraints_evaluated
        matched = all_passed if constraints_evaluated > 0 else True

        if matched:
            if policy.effect == PolicyEffect.ALLOW:
                decision = "allowed"
                score = 1.0
            elif policy.effect == PolicyEffect.DENY:
                decision = "denied"
                score = 0.0
            elif policy.effect == PolicyEffect.WARN:
                decision = "warning"
                score = 0.5
            elif policy.effect == PolicyEffect.REQUIRE_APPROVAL:
                decision = "requires_approval"
                score = 0.3
            elif policy.effect == PolicyEffect.ESCALATE:
                decision = "escalated"
                score = 0.2
            elif policy.effect == PolicyEffect.RETRY:
                decision = "retry"
                score = 0.4
            elif policy.effect == PolicyEffect.ROLLBACK:
                decision = "rollback"
                score = 0.1
            else:
                decision = "custom"
                score = 0.5
        else:
            decision = "not_applicable"
            score = 1.0

        result = PolicyEvaluationResult(
            id=result_id,
            policy_id=policy.id,
            policy_name=policy.name,
            type=policy.type,
            effect=policy.effect,
            matched=matched,
            decision=decision,
            score=score,
            constraints_evaluated=constraints_evaluated,
            constraints_passed=constraints_passed,
            details=details,
        )
        self._telemetry["policies_evaluated"] += 1
        return result

    def _resolve_field(self, context: dict, field_path: str) -> Any:
        parts = field_path.split(".")
        value = context
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            elif isinstance(value, list) and part.lstrip("-").isdigit():
                idx = int(part)
                value = value[idx] if 0 <= idx < len(value) else None
            else:
                return None
        return value

    def _evaluate_constraint(self, operator: ConstraintOperator, actual: Any, expected: Any) -> bool:
        if operator == ConstraintOperator.EQUALS:
            return actual == expected
        elif operator == ConstraintOperator.NOT_EQUALS:
            return actual != expected
        elif operator == ConstraintOperator.GREATER_THAN:
            try:
                return float(actual) > float(expected)
            except (TypeError, ValueError):
                return False
        elif operator == ConstraintOperator.LESS_THAN:
            try:
                return float(actual) < float(expected)
            except (TypeError, ValueError):
                return False
        elif operator == ConstraintOperator.IN:
            if isinstance(expected, list):
                return actual in expected
            return False
        elif operator == ConstraintOperator.NOT_IN:
            if isinstance(expected, list):
                return actual not in expected
            return False
        elif operator == ConstraintOperator.CONTAINS:
            if isinstance(actual, str) and isinstance(expected, str):
                return expected in actual
            if isinstance(actual, list):
                return expected in actual
            return False
        elif operator == ConstraintOperator.NOT_CONTAINS:
            if isinstance(actual, str) and isinstance(expected, str):
                return expected not in actual
            if isinstance(actual, list):
                return expected not in actual
            return False
        elif operator == ConstraintOperator.MATCHES:
            if isinstance(actual, str) and isinstance(expected, str):
                try:
                    return bool(re.search(expected, actual))
                except re.error:
                    return False
            return False
        elif operator == ConstraintOperator.EXISTS:
            return actual is not None
        elif operator == ConstraintOperator.NOT_EXISTS:
            return actual is None
        return False

    def evaluate_all(self, org_id: str, type: PolicyType, context: dict) -> list[PolicyEvaluationResult]:
        self._telemetry["evaluate_all_calls"] += 1
        policies = self.list_policies(org_id=org_id, type=type, status=PolicyStatus.ACTIVE)
        results = []
        for policy in sorted(policies, key=lambda p: p.priority, reverse=True):
            result = self.evaluate_policy(policy, context)
            results.append(result)
        return results

    def evaluate_and_enforce(self, org_id: str, type: PolicyType, context: dict) -> dict:
        self._telemetry["evaluate_and_enforce_calls"] += 1
        results = self.evaluate_all(org_id, type, context)
        decisions = [r.decision for r in results if r.matched]

        if "denied" in decisions:
            final_decision = "denied"
        elif "escalated" in decisions:
            final_decision = "escalated"
        elif "rollback" in decisions:
            final_decision = "rollback"
        elif "requires_approval" in decisions:
            final_decision = "requires_approval"
        elif "retry" in decisions:
            final_decision = "retry"
        elif "warning" in decisions:
            final_decision = "warning"
        elif "custom" in decisions:
            final_decision = "custom"
        else:
            final_decision = "allowed"

        return {
            "decision": final_decision,
            "org_id": org_id,
            "type": type.value,
            "policies_evaluated": len(results),
            "matched_policies": [r.policy_id for r in results if r.matched],
            "results": [r.to_dict() for r in results],
        }

    def simulate_policy(self, org_id: str, scenario_name: str, policy_ids: list[str], context: dict) -> PolicySimulationResult:
        self._telemetry["simulate_policy_calls"] += 1
        results = []
        total_passed = 0
        total_failed = 0
        total_warnings = 0
        recommendations = []

        for pid in policy_ids:
            policy = self._policies.get(pid)
            if not policy:
                continue
            result = self.evaluate_policy(policy, context)
            results.append(result)
            if result.decision == "allowed":
                total_passed += 1
            elif result.decision == "denied":
                total_failed += 1
            elif result.decision == "warning":
                total_warnings += 1
            if not result.matched:
                recommendations.append(f"Policy '{policy.name}' ({policy.id}) did not match context — consider reviewing constraints.")

        sim_result = PolicySimulationResult(
            id=str(uuid.uuid4()),
            org_id=org_id,
            scenario_name=scenario_name,
            policies_evaluated=len(results),
            total_passed=total_passed,
            total_failed=total_failed,
            total_warnings=total_warnings,
            results=results,
            recommendations=recommendations,
        )
        self._telemetry["simulations_run"] += 1
        return sim_result

    def test_policy(self, policy_id: str, test_cases: list[dict]) -> dict:
        self._telemetry["test_policy_calls"] += 1
        policy = self._policies.get(policy_id)
        if not policy:
            return {"error": f"Policy {policy_id} not found", "test_cases": len(test_cases), "passed": 0, "failed": 0}

        passed = 0
        failed = 0
        case_results = []
        for i, case in enumerate(test_cases):
            context = case.get("context", {})
            expected_decision = case.get("expected_decision")
            result = self.evaluate_policy(policy, context)
            match = result.decision == expected_decision if expected_decision else result.matched
            if match:
                passed += 1
            else:
                failed += 1
            case_results.append({
                "case_index": i,
                "expected": expected_decision,
                "actual": result.decision,
                "matched": result.matched,
                "passed": match,
                "details": result.details,
            })

        return {
            "policy_id": policy_id,
            "policy_name": policy.name,
            "test_cases": len(test_cases),
            "passed": passed,
            "failed": failed,
            "results": case_results,
        }

    def get_policy_stats(self, org_id: Optional[str] = None) -> dict:
        self._telemetry["get_policy_stats_calls"] += 1
        policies = self.list_policies(org_id=org_id) if org_id else list(self._policies.values())
        type_counts = defaultdict(int)
        status_counts = defaultdict(int)
        severity_counts = defaultdict(int)
        for p in policies:
            type_counts[p.type.value] += 1
            status_counts[p.status.value] += 1
            severity_counts[p.severity.value] += 1
        return {
            "total_policies": len(policies),
            "total_versions": sum(len(v) for v in self._versions.values()),
            "total_audit_entries": len(self._audit_log),
            "type_distribution": dict(type_counts),
            "status_distribution": dict(status_counts),
            "severity_distribution": dict(severity_counts),
            "telemetry": dict(self._telemetry),
        }

    def get_telemetry(self) -> dict:
        return dict(self._telemetry)
