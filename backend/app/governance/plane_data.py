"""Data governance — Volume 71 Commit 2.

Delegates to V65 placement/residency and V57/V68 data authorities
(catalog, lineage, classification, retention, exports, processors).
Adds central policy evaluation on top; never duplicates catalog or
lineage storage.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.governance.plane_common import ValidationError, sanitize_context
from app.governance.plane_evaluate import evaluate


async def govern_data_access(
    db: AsyncSession, tenant: str, *,
    dataset: str = "", project: str = "", workspace: str = "",
    classification: str = "INTERNAL", region: str = "",
    destination: str = "", operation: str = "data.access",
    actor: str = "",
) -> dict:
    if not tenant:
        raise ValidationError("tenant required")
    context = sanitize_context({
        "tenant": tenant, "workspace": workspace, "project": project,
        "dataset": dataset, "resource": dataset,
        "classification": classification, "region": region,
        "operation": operation, "actor": actor,
    })
    result = await evaluate(db, tenant, scope_type="workspace" if workspace else "tenant",
                            scope_value=workspace, operation=operation,
                            context=context, actor=actor)
    if result["decision"] == "DENY":
        return {**result, "allowed": False, "layer": "governance"}

    residency: dict = {"decision": "ALLOW"}
    if region or destination:
        try:
            from app.regions.placement import placement_service
            check = await placement_service.evaluate(
                db, tenant, classification or "INTERNAL", region or destination,
                actor=actor)
            residency = {"decision": check.get("decision", "ALLOW"),
                         "reason": check.get("reason", "")}
            if residency["decision"] == "DENY":
                return {**result, "decision": "DENY", "allowed": False,
                        "layer": "residency",
                        "reason": f"residency denied: {residency['reason']}"}
        except Exception:
            residency = {"decision": "ALLOW"}
    return {**result, "allowed": result["decision"] == "ALLOW",
            "layer": "governance+residency", "residency": residency["decision"]}
