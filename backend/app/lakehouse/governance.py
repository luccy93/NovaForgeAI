"""Data Governance - access policies, roles, compliance checks and audit trails."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class GovernancePolicy:
    resource: str          # dataset / table / metric name or wildcard "*"
    role: str              # owner | admin | analyst | auditor | viewer
    allow_read: bool = True
    allow_write: bool = False
    allow_export: bool = False
    notes: str = ""


@dataclass
class GovernanceRule:
    """Custom override rule: resource prefix + role -> action allowances."""
    resource: str
    role: str
    allow_read: bool = True
    allow_write: bool = False
    allow_export: bool = False


@dataclass
class GovernanceDecision:
    resource: str
    role: str
    action: str  # read | write | export
    allowed: bool
    reason: str
    at: str = ""


class GovernanceEngine:
    """Role-based access decisions for data resources with an audit trail."""

    DEFAULT_MATRIX = {
        "owner":   {"read": True, "write": True, "export": True},
        "admin":   {"read": True, "write": True, "export": True},
        "analyst": {"read": True, "write": False, "export": True},
        "auditor": {"read": True, "write": False, "export": False},
        "viewer":  {"read": True, "write": False, "export": False},
    }

    def __init__(self, extra_rules: Optional[list[GovernanceRule]] = None):
        self.rules: list[GovernanceRule] = list(extra_rules or [])
        self.decisions: list[GovernanceDecision] = []

    def add_rule(self, rule: GovernanceRule) -> None:
        self.rules.append(rule)

    def can(self, resource: str, role: str, action: str = "read") -> bool:
        result = self.decide(resource, role, action)
        return result.allowed

    def decide(self, resource: str, role: str, action: str) -> GovernanceDecision:
        allowed = self.DEFAULT_MATRIX.get(role, {}).get(action, False)
        reason = f"default policy for role={role}, action={action}"
        for rule in self.rules:
            if rule.role == role:
                if rule.resource == "*" or resource.startswith(rule.resource):
                    allowed = getattr(rule, f"allow_{action}", allowed)
                    reason = f"rule matched resource='{rule.resource}'"
        decision = GovernanceDecision(resource, role, action, allowed, reason,
                                      datetime.now(timezone.utc).isoformat())
        self.decisions.append(decision)
        return decision

    def audit_trail(self, limit: int = 100) -> list[dict]:
        return [{"resource": d.resource, "role": d.role, "action": d.action,
                 "allowed": d.allowed, "reason": d.reason, "at": d.at}
                for d in self.decisions[-limit:]]

    def compliance_summary(self) -> dict:
        total = len(self.decisions)
        denied = sum(1 for d in self.decisions if not d.allowed)
        return {"decisions": total,
                "denied": denied,
                "denial_rate": round(denied / total, 4) if total else 0.0,
                "rule_count": len(self.rules)}