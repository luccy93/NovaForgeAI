"""Workflow/agent governance — Volume 71 Commit 2.

Pre-execution policy gates for workflow runs and agent steps:
approval requirements, executor identity, fan-out caps, environment
and classification limits, tool/step budgets and release gates.
Execution itself stays in V66/V67; approvals use existing controls.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.governance.plane_common import ValidationError, sanitize_context
from app.governance.plane_evaluate import evaluate


async def govern_workflow_run(
    db: AsyncSession, tenant: str, *,
    workflow_id: str = "", run_id: str = "", executor: str = "",
    environment: str = "", classification: str = "INTERNAL",
    fan_out: int = 1, max_fan_out: int = 5, actor: str = "",
) -> dict:
    if not tenant:
        raise ValidationError("tenant required")
    try:
        fan_out = int(fan_out or 1)
        max_fan_out = int(max_fan_out or 5)
    except (TypeError, ValueError):
        raise ValidationError("fan_out bounds must be integers")
    if fan_out > max_fan_out:
        return {"decision": "BLOCK", "allowed": False, "layer": "governance",
                "reason": f"fan-out {fan_out} exceeds maximum {max_fan_out}",
                "scope_type": "tenant", "scope_value": ""}
    context = sanitize_context({
        "tenant": tenant, "workflow": workflow_id, "resource": run_id,
        "operation": "workflow.run", "environment": environment,
        "classification": classification, "actor": actor or executor,
    })
    result = await evaluate(db, tenant, scope_type="tenant", scope_value="",
                            operation="workflow.run", context=context, actor=actor)
    return {**result, "allowed": result["decision"] == "ALLOW",
            "layer": "governance"}


async def govern_agent_step(
    db: AsyncSession, tenant: str, *,
    agent: str = "", tool: str = "", step_number: int = 0,
    max_steps: int = 25, classification: str = "INTERNAL",
    actor: str = "",
) -> dict:
    if not tenant:
        raise ValidationError("tenant required")
    try:
        step_number = int(step_number or 0)
        max_steps = int(max_steps or 25)
    except (TypeError, ValueError):
        raise ValidationError("step bounds must be integers")
    if step_number > max_steps:
        return {"decision": "BLOCK", "allowed": False, "layer": "governance",
                "reason": f"step {step_number} exceeds maximum {max_steps}",
                "scope_type": "tenant", "scope_value": ""}
    context = sanitize_context({
        "tenant": tenant, "operation": "agent.step", "resource": tool,
        "classification": classification, "actor": actor or agent,
    })
    result = await evaluate(db, tenant, scope_type="tenant", scope_value="",
                            operation="agent.step", context=context, actor=actor)
    return {**result, "allowed": result["decision"] == "ALLOW",
            "layer": "governance"}
