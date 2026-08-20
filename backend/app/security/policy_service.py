"""Security policy evaluation service (Volume 47).

Integrates with the governance policy engine for security gate
decisions (ALLOW/WARN/BLOCK/REQUIRE_APPROVAL).
"""

import logging
from typing import Optional

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.security.models import SecurityPolicy, SecurityPolicyEvaluation

logger = logging.getLogger(__name__)

DEFAULT_SECURITY_RULES = [
    {
        "name": "block_critical_secrets",
        "description": "Block if critical secrets are detected",
        "conditions": {"severity": "critical", "finding_type": "secret"},
        "action": "block",
        "priority": 100,
    },
    {
        "name": "warn_high_sast",
        "description": "Warn on high-severity SAST findings",
        "conditions": {"severity": "high", "finding_type": "sast"},
        "action": "warn",
        "priority": 90,
    },
    {
        "name": "block_critical_dependency",
        "description": "Block if critical dependency vulnerabilities exist",
        "conditions": {"severity": "critical", "finding_type": "dependency"},
        "action": "block",
        "priority": 95,
    },
    {
        "name": "require_approval_iac",
        "description": "Require approval for IaC issues",
        "conditions": {"severity": "high", "finding_type": "iac"},
        "action": "require_approval",
        "priority": 85,
    },
    {
        "name": "allow_informational",
        "description": "Allow informational findings",
        "conditions": {"severity": "informational"},
        "action": "allow",
        "priority": 50,
    },
]


class PolicyService:
    """Security gate policies with conditions, actions, and evaluations."""

    async def create_policy(
        self,
        db: AsyncSession,
        *,
        tenant: str,
        name: str,
        description: str = "",
        policy_type: str = "gate",
        scope: str = "repository",
        conditions: Optional[dict] = None,
        actions: Optional[dict] = None,
        priority: int = 100,
        tags: Optional[list] = None,
    ) -> SecurityPolicy:
        policy = SecurityPolicy(
            tenant=tenant,
            name=name,
            description=description,
            policy_type=policy_type,
            scope=scope,
            conditions=conditions or {},
            actions=actions or {"decision": "warn"},
            priority=priority,
            tags=tags or [],
        )
        db.add(policy)
        await db.flush()
        return policy

    async def get_policy(self, db: AsyncSession, policy_id) -> SecurityPolicy | None:
        stmt = select(SecurityPolicy).where(SecurityPolicy.id == policy_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_policies(
        self,
        db: AsyncSession,
        *,
        tenant: str,
        policy_type: str | None = None,
        enabled_only: bool = True,
        limit: int = 50,
    ) -> list[SecurityPolicy]:
        stmt = select(SecurityPolicy).where(SecurityPolicy.tenant == tenant)
        if enabled_only:
            stmt = stmt.where(SecurityPolicy.enabled == True)
        if policy_type:
            stmt = stmt.where(SecurityPolicy.policy_type == policy_type)
        stmt = stmt.order_by(SecurityPolicy.priority.desc()).limit(limit)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def update_policy(self, db: AsyncSession, policy_id, **kwargs) -> SecurityPolicy | None:
        policy = await self.get_policy(db, policy_id)
        if not policy:
            return None
        for key, value in kwargs.items():
            if hasattr(policy, key):
                setattr(policy, key, value)
        policy.version += 1
        await db.flush()
        return policy

    async def evaluate(
        self,
        db: AsyncSession,
        *,
        tenant: str,
        target_type: str,
        target_id: str,
        findings: list[dict],
    ) -> dict:
        policies = await self.list_policies(db, tenant=tenant)
        all_findings_list = list(findings)
        decisions = []
        overall = "allow"
        severity_scores = {"critical": 10, "high": 7, "medium": 4, "low": 2, "informational": 1}

        for policy in policies:
            conditions = policy.conditions
            matched = []
            for finding in all_findings_list:
                match = True
                for key, value in conditions.items():
                    if finding.get(key) != value:
                        match = False
                        break
                if match:
                    matched.append(finding)

            if matched:
                action = policy.actions.get("decision", "warn")
                max_severity = max((severity_scores.get(f.get("severity", "low"), 1) for f in matched), default=0)
                eval_rec = SecurityPolicyEvaluation(
                    policy_id=policy.id,
                    tenant=tenant,
                    target_type=target_type,
                    target_id=target_id,
                    decision=action,
                    score=float(max_severity),
                    reason=f"Matched {len(matched)} findings against policy '{policy.name}'",
                    matched_conditions=[{"rule": f.get("rule", ""), "severity": f.get("severity", "")} for f in matched[:10]],
                )
                db.add(eval_rec)
                decisions.append({
                    "policy_id": str(policy.id),
                    "policy_name": policy.name,
                    "decision": action,
                    "matched_count": len(matched),
                })
                if action == "block":
                    overall = "block"
                elif action == "require_approval" and overall != "block":
                    overall = "require_approval"
                elif action == "warn" and overall == "allow":
                    overall = "warn"

        await db.flush()
        return {"overall_decision": overall, "evaluations": decisions, "policy_count": len(policies)}

    async def get_evaluation_history(
        self,
        db: AsyncSession,
        *,
        tenant: str,
        policy_id=None,
        limit: int = 20,
    ) -> list[SecurityPolicyEvaluation]:
        stmt = select(SecurityPolicyEvaluation).where(SecurityPolicyEvaluation.tenant == tenant)
        if policy_id:
            stmt = stmt.where(SecurityPolicyEvaluation.policy_id == policy_id)
        stmt = stmt.order_by(SecurityPolicyEvaluation.created_at.desc()).limit(limit)
        result = await db.execute(stmt)
        return list(result.scalars().all())


policy_service = PolicyService()
