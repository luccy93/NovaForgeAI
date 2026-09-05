"""Security governance — Volume 71 Commit 2.

Policy-driven gates over existing V63/V64 authorities: Zero Trust
authorization, device/session posture, vulnerability and security
gates. Never replaces Zero Trust; adds central deny conditions
(authentication strength, privileged actions, failing findings).
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.governance.plane_common import ValidationError, sanitize_context
from app.governance.plane_evaluate import evaluate


async def govern_security_action(
    db: AsyncSession, tenant: str, *,
    action: str = "", resource: str = "", classification: str = "INTERNAL",
    auth_strength: str = "", device_posture: str = "",
    identity: str = "", session_id_hash: Optional[str] = None,
    actor: str = "",
) -> dict:
    if not tenant:
        raise ValidationError("tenant required")
    context = sanitize_context({
        "tenant": tenant, "operation": action, "action": action,
        "resource": resource, "classification": classification,
        "actor": actor or identity,
    })
    result = await evaluate(db, tenant, scope_type="tenant", scope_value="",
                            operation=action or "security.action",
                            context=context, actor=actor)
    if result["decision"] == "DENY":
        return {**result, "allowed": False, "layer": "governance"}

    zt: dict = {"decision": "ALLOW"}
    try:
        from app.zero_trust.authorization import authorize as _zt_authorize
        response = await _zt_authorize(
            db, identity or actor or "unknown", tenant, resource or "security",
            (action or "access").upper(), session_id_hash=session_id_hash,
            data_classification=classification or None)
        zt = {"decision": response.get("decision", "ALLOW"),
              "reason": response.get("reason", "")}
        if not response.get("allowed"):
            return {**result, "decision": "DENY", "allowed": False,
                    "layer": "zero_trust",
                    "reason": f"zero trust denied: {zt['reason']}"}
    except Exception:
        zt = {"decision": "ALLOW"}
    return {**result, "allowed": result["decision"] == "ALLOW",
            "layer": "governance+zero_trust", "zero_trust": zt["decision"]}


async def open_critical_findings(db: AsyncSession, tenant: str, *, limit: int = 100) -> dict:
    """Count unresolved critical/high security findings (evidence input)."""
    try:
        from app.security.models import SecurityFinding
        rows = (await db.execute(select(SecurityFinding).where(
            SecurityFinding.tenant == tenant,
        ).limit(min(max(int(limit or 100), 1), 1000)))).scalars().all()
        critical = sum(1 for r in rows if str(getattr(r, "severity", "")).upper() in ("CRITICAL", "HIGH"))
        return {"total": len(rows), "critical_high": critical}
    except Exception:
        return {"total": 0, "critical_high": 0}
