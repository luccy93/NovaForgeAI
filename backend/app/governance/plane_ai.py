"""AI governance — Volume 71 Commit 2.

Wraps (never replaces) the AI Gateway and V67 usage accounting:
central AI policies for model/provider/use-case/action-classification,
token and cost ceilings via V69 FinOps, human approval via existing
workflow approvals. Prohibited operations are denied outright.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.governance.plane_common import ValidationError, sanitize_context
from app.governance.plane_evaluate import evaluate


async def govern_ai_request(
    db: AsyncSession, tenant: str, *,
    model: str = "", provider: str = "", use_case: str = "",
    action_class: str = "", classification: str = "INTERNAL",
    input_tokens: int = 0, estimated_cents: int = 0,
    actor: str = "", operation: str = "ai.invoke",
) -> dict:
    """Evaluate central AI policies, then FinOps ceilings. Returns a
    unified decision; callers must enforce BLOCK/REQUIRE_APPROVAL."""
    if not tenant:
        raise ValidationError("tenant required")
    context = sanitize_context({
        "tenant": tenant, "model": model, "provider": provider,
        "operation": operation, "action": action_class or use_case,
        "classification": classification, "actor": actor,
        "cost_cents": estimated_cents,
    })
    result = await evaluate(db, tenant, scope_type="tenant", scope_value="",
                            operation=operation, context=context, actor=actor)
    if result["decision"] == "DENY":
        return {**result, "allowed": False, "layer": "governance"}

    finops_gate: dict = {"decision": "ALLOW"}
    if estimated_cents and estimated_cents > 0:
        try:
            from app.finops.governance import evaluate_operation as _finops_gate
            finops_gate = await _finops_gate(
                db, tenant, actor or "ai", operation,
                estimated_cents=int(estimated_cents),
                usage={"input_tokens": int(input_tokens or 0), "requests": 1},
                model=model, provider=provider)
            if finops_gate.get("decision") == "BLOCK":
                return {**result, "decision": "BLOCK", "allowed": False,
                        "layer": "finops",
                        "reason": f"finops ceiling: {finops_gate.get('reason', '')}"}
        except ValidationError:
            raise
        except Exception:
            finops_gate = {"decision": "ALLOW"}
    allowed = result["decision"] == "ALLOW" and finops_gate.get("decision") in ("ALLOW", "WARN", None)
    return {**result, "allowed": allowed, "layer": "governance+finops",
            "finops_gate": finops_gate.get("decision", "ALLOW")}
