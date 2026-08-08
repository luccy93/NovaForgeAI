"""AI Governance — policies for AI, models, prompts, tools, memory, security, cost, and usage with enforcement and auditing."""

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class PolicyDomain(Enum):
    AI = "ai"
    MODEL = "model"
    PROMPT = "prompt"
    TOOL = "tool"
    MEMORY = "memory"
    SECURITY = "security"
    COST = "cost"
    USAGE = "usage"


class PolicyEffect(Enum):
    ALLOW = "allow"
    DENY = "deny"
    WARN = "warn"
    AUDIT = "audit"
    REQUIRE_APPROVAL = "require_approval"


class ViolationSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Policy:
    id: str
    domain: PolicyDomain
    name: str
    description: str
    rule: str  # expression or condition
    effect: PolicyEffect
    priority: int = 0  # higher = more important
    enabled: bool = True
    created_at: str = ""
    updated_at: str = ""


@dataclass
class PolicyViolation:
    id: str
    policy_id: str
    policy_name: str
    domain: PolicyDomain
    severity: ViolationSeverity
    message: str
    context: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""
    acknowledged: bool = False


@dataclass
class GovernanceReport:
    repo_id: str
    repo_name: str
    timestamp: str
    policies: list[Policy] = field(default_factory=list)
    violations: list[PolicyViolation] = field(default_factory=list)
    policy_count: int = 0
    enabled_policies: int = 0
    active_violations: int = 0
    critical_violations: int = 0
    high_violations: int = 0
    compliance_score: float = 100.0
    recommendations: list[str] = field(default_factory=list)


class AIGovernance:
    """AI Governance framework — defines, enforces, and audits policies across all AI domains."""

    DEFAULT_POLICIES = [
        Policy(id="", domain=PolicyDomain.SECURITY, name="No secrets in prompts",
               description="Prompts must not contain API keys, passwords, or tokens",
               rule="no_secrets_in_prompts", effect=PolicyEffect.DENY, priority=100),
        Policy(id="", domain=PolicyDomain.MODEL, name="Minimum model quality",
               description="Only use models with >= 70% accuracy for production tasks",
               rule="min_model_accuracy >= 0.7", effect=PolicyEffect.WARN, priority=80),
        Policy(id="", domain=PolicyDomain.COST, name="Cost per operation limit",
               description="Maximum $0.10 per AI operation",
               rule="cost_per_operation <= 0.10", effect=PolicyEffect.WARN, priority=70),
        Policy(id="", domain=PolicyDomain.MEMORY, name="Memory TTL",
               description="Conversation memory expires after 90 days",
               rule="memory_ttl_days <= 90", effect=PolicyEffect.AUDIT, priority=60),
        Policy(id="", domain=PolicyDomain.USAGE, name="Rate limiting",
               description="Maximum 100 AI requests per minute",
               rule="requests_per_minute <= 100", effect=PolicyEffect.DENY, priority=90),
        Policy(id="", domain=PolicyDomain.PROMPT, name="No PII in prompts",
               description="Prompts must not contain personally identifiable information",
               rule="no_pii_in_prompts", effect=PolicyEffect.DENY, priority=100),
        Policy(id="", domain=PolicyDomain.TOOL, name="Approved tools only",
               description="Only use tools from the approved tool list",
               rule="tool_in_approved_list", effect=PolicyEffect.DENY, priority=85),
        Policy(id="", domain=PolicyDomain.AI, name="Human oversight for critical decisions",
               description="Critical decisions require human approval",
               rule="critical_decision_needs_approval", effect=PolicyEffect.REQUIRE_APPROVAL, priority=95),
    ]

    def __init__(self, repo_path: str = ""):
        self.repo_path = Path(repo_path) if repo_path else Path()
        self.policies: dict[str, Policy] = {}
        self.violations: list[PolicyViolation] = []
        self._violation_counters: dict[str, int] = defaultdict(int)
        self._init_defaults()

    def _init_defaults(self):
        for p in self.DEFAULT_POLICIES:
            pid = f"pol-{uuid.uuid4().hex[:12]}"
            p.id = pid
            p.created_at = datetime.now(timezone.utc).isoformat()
            p.updated_at = datetime.now(timezone.utc).isoformat()
            self.policies[pid] = p

    def add_policy(self, domain: PolicyDomain, name: str, description: str,
                   rule: str, effect: PolicyEffect, priority: int = 0) -> Policy:
        pid = f"pol-{uuid.uuid4().hex[:12]}"
        policy = Policy(
            id=pid, domain=domain, name=name, description=description,
            rule=rule, effect=effect, priority=priority,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        self.policies[pid] = policy
        return policy

    def evaluate(self, domain: PolicyDomain, action: str, context: dict = None) -> list[PolicyViolation]:
        violations = []
        for policy in self.policies.values():
            if not policy.enabled or policy.domain != domain:
                continue
            if self._matches_rule(policy.rule, action, context):
                violation = PolicyViolation(
                    id=f"viol-{uuid.uuid4().hex[:12]}",
                    policy_id=policy.id,
                    policy_name=policy.name,
                    domain=policy.domain,
                    severity=self._determine_severity(policy.effect),
                    message=f"Policy violation: {policy.name} — {policy.description}",
                    context=context or {},
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
                violations.append(violation)
                self.violations.append(violation)
                self._violation_counters[policy.id] += 1
        return violations

    def _matches_rule(self, rule: str, action: str, context: dict = None) -> bool:
        action_lower = action.lower()
        context = context or {}

        if "secret" in rule and "secret" in action_lower:
            return True
        if "pii" in rule and ("email" in action_lower or "ssn" in action_lower or "phone" in action_lower):
            return True
        if "cost" in rule:
            cost = context.get("cost", 0)
            if cost > 0.10:
                return True
        if "rate" in rule:
            rate = context.get("requests_per_minute", 0)
            if rate > 100:
                return True
        if "memory" in rule:
            ttl = context.get("ttl_days", 365)
            if ttl > 90:
                return True
        if "approval" in rule:
            severity = context.get("severity", "").lower()
            if severity in ("critical", "high"):
                return True
        return False

    def _determine_severity(self, effect: PolicyEffect) -> ViolationSeverity:
        mapping = {
            PolicyEffect.DENY: ViolationSeverity.CRITICAL,
            PolicyEffect.REQUIRE_APPROVAL: ViolationSeverity.HIGH,
            PolicyEffect.WARN: ViolationSeverity.MEDIUM,
            PolicyEffect.AUDIT: ViolationSeverity.LOW,
            PolicyEffect.ALLOW: ViolationSeverity.LOW,
        }
        return mapping.get(effect, ViolationSeverity.MEDIUM)

    def acknowledge_violation(self, violation_id: str) -> bool:
        for v in self.violations:
            if v.id == violation_id:
                v.acknowledged = True
                return True
        return False

    def enable_policy(self, policy_id: str, enabled: bool = True) -> bool:
        policy = self.policies.get(policy_id)
        if policy:
            policy.enabled = enabled
            policy.updated_at = datetime.now(timezone.utc).isoformat()
            return True
        return False

    def get_active_violations(self, domain: Optional[PolicyDomain] = None) -> list[PolicyViolation]:
        unacknowledged = [v for v in self.violations if not v.acknowledged]
        if domain:
            unacknowledged = [v for v in unacknowledged if v.domain == domain]
        return sorted(unacknowledged, key=lambda v: v.timestamp, reverse=True)

    def generate_report(self) -> GovernanceReport:
        active_violations = self.get_active_violations()
        report = GovernanceReport(
            repo_id=str(hash(str(self.repo_path))),
            repo_name=self.repo_path.name,
            timestamp=datetime.now(timezone.utc).isoformat(),
            policies=list(self.policies.values()),
            violations=self.violations[-100:],
            policy_count=len(self.policies),
            enabled_policies=sum(1 for p in self.policies.values() if p.enabled),
            active_violations=len(active_violations),
            critical_violations=sum(1 for v in active_violations if v.severity == ViolationSeverity.CRITICAL),
            high_violations=sum(1 for v in active_violations if v.severity == ViolationSeverity.HIGH),
        )

        total_checks = len(active_violations) + max(len(self.policies), 1)
        report.compliance_score = round(
            (1 - len(active_violations) / max(total_checks, 1)) * 100, 1
        )

        if report.critical_violations > 0:
            report.recommendations.append(f"Address {report.critical_violations} critical policy violations immediately")
        if report.high_violations > 0:
            report.recommendations.append(f"Review {report.high_violations} high-severity violations")
        if report.compliance_score < 80:
            report.recommendations.append("Overall compliance score below 80% — schedule policy review")
        disabled = len(self.policies) - report.enabled_policies
        if disabled > 0:
            report.recommendations.append(f"{disabled} policies are disabled — review if still needed")

        return report


from collections import defaultdict  # noqa: E402
