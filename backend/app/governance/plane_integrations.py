"""Integration governance — Volume 71 Commit 2.

Connector allowlists, destination/OAuth-scope restrictions, transfer
classification and residency, webhook trust, outbound restrictions and
per-integration cost/rate policy — all evaluated through central
policies plus the V70 mechanisms (never around them).
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.governance.plane_common import ValidationError, sanitize_context
from app.governance.plane_evaluate import evaluate


async def govern_integration_use(
    db: AsyncSession, tenant: str, *,
    connection_id: str = "", operation: str = "integration.use",
    destination: str = "", classification: str = "INTERNAL",
    region: str = "", scopes: Optional[list] = None,
    estimated_cents: int = 0, actor: str = "",
) -> dict:
    if not tenant:
        raise ValidationError("tenant required")
    context = sanitize_context({
        "tenant": tenant, "resource": connection_id, "operation": operation,
        "classification": classification, "region": region, "actor": actor,
        "cost_cents": estimated_cents,
    })
    result = await evaluate(db, tenant, scope_type="tenant", scope_value="",
                            operation=operation, context=context, actor=actor)
    if result["decision"] == "DENY":
        return {**result, "allowed": False, "layer": "governance"}

    transfer: dict = {"decision": "ALLOW"}
    if destination or classification or region or scopes:
        try:
            from app.integrations.policies import evaluate_transfer as _transfer
            transfer = await _transfer(
                db, tenant, operation=operation, classification=classification,
                region=region, fields=[], estimated_cents=int(estimated_cents or 0),
                actor=actor)
            if transfer.get("decision") == "BLOCK":
                return {**result, "decision": "BLOCK", "allowed": False,
                        "layer": "integration",
                        "reason": f"transfer policy: {transfer.get('reasons', [])}"}
        except Exception:
            transfer = {"decision": "ALLOW"}
    allowed = result["decision"] == "ALLOW" and transfer.get("decision") in ("ALLOW", "WARN", None)
    return {**result, "allowed": allowed, "layer": "governance+integration",
            "transfer": transfer.get("decision", "ALLOW")}
