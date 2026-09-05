"""FinOps governance — Volume 71 Commit 2.

Budget enforcement, cost ceilings, model/provider restrictions and
expensive-operation approval over V69 authoritative records. No
parallel cost accounting is created here.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.governance.plane_common import ValidationError, sanitize_context
from app.governance.plane_evaluate import evaluate


async def govern_spend(
    db: AsyncSession, tenant: str, *,
    operation: str = "spend", model: str = "", provider: str = "",
    workspace: str = "", project: str = "", estimated_cents: int = 0,
    budget_id=None, actor: str = "",
) -> dict:
    if not tenant:
        raise ValidationError("tenant required")
    context = sanitize_context({
        "tenant": tenant, "workspace": workspace, "project": project,
        "model": model, "provider": provider, "operation": operation,
        "cost_cents": estimated_cents, "actor": actor,
    })
    result = await evaluate(db, tenant,
                            scope_type="workspace" if workspace else "tenant",
                            scope_value=workspace, operation=operation,
                            context=context, actor=actor)
    if result["decision"] == "DENY":
        return {**result, "allowed": False, "layer": "governance"}

    budget_state: dict = {}
    if budget_id:
        try:
            from app.finops.budgets import evaluate_budget as _evaluate_budget
            budget_state = await _evaluate_budget(db, tenant, budget_id, actor=actor)
            if budget_state.get("status") == "EXCEEDED":
                return {**result, "decision": "BLOCK", "allowed": False,
                        "layer": "finops",
                        "reason": f"budget {budget_id} exceeded"}
        except Exception as exc:
            budget_state = {"error": f"{type(exc).__name__}"}

    gate: dict = {"decision": "ALLOW"}
    try:
        from app.finops.governance import evaluate_operation as _finops_gate
        gate = await _finops_gate(db, tenant, actor or "governance", operation,
                                  estimated_cents=int(estimated_cents or 0),
                                  workspace=workspace, project=project,
                                  model=model, provider=provider)
        if gate.get("decision") == "BLOCK":
            return {**result, "decision": "BLOCK", "allowed": False,
                    "layer": "finops", "reason": f"finops gate: {gate.get('reason', '')}"}
    except Exception:
        gate = {"decision": "ALLOW"}
    allowed = result["decision"] == "ALLOW" and gate.get("decision") in ("ALLOW", "WARN", None)
    return {**result, "allowed": allowed, "layer": "governance+finops",
            "finops_gate": gate.get("decision", "ALLOW"), "budget": budget_state}
