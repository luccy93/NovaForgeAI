"""Agents API v2 — connects to the new Volume 9 agent framework."""

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.models.support import AgentRun
from app.schemas import (
    AgentRunResponse, PipelineResponse, ParallelResponse,
)
from app.api.auth import _get_current_user
from app.agents import registry
from app.agents.schemas import AgentConfig, AgentRole, RetryPolicy
from app.agents.workflow import AgentWorkflow, WorkflowNode

router = APIRouter()


@router.on_event("startup")
async def discover_agents():
    registry.discover()


@router.get("", response_model=list[dict[str, Any]])
async def list_agents():
    """List all available agents with descriptions."""
    return registry.list_agents()


@router.get("/{agent_name}", response_model=dict[str, Any])
async def get_agent_info(agent_name: str):
    """Get detailed information about a specific agent."""
    config = registry.get_config(agent_name)
    if not config:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")
    return {
        "name": config.name,
        "role": config.role.value,
        "version": config.version,
        "description": config.description,
        "goals": config.goals,
        "model": config.model,
        "temperature": config.temperature,
        "permissions": config.permissions,
        "require_human_approval": config.require_human_approval,
    }


@router.post("/{agent_name}/run", response_model=dict[str, Any])
async def run_agent(
    agent_name: str,
    task_input: str = Query(..., min_length=1, max_length=10000),
    organization_id: Optional[str] = Query(None),
    repository_id: Optional[str] = Query(None),
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run a single agent with the given task."""
    agent = registry.get_agent(agent_name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    context = {"organization_id": organization_id, "repository_id": repository_id}
    result = await agent.run(task_input, context)

    run_id = str(uuid.uuid4())
    run = AgentRun(
        id=uuid.UUID(run_id),
        organization_id=uuid.UUID(organization_id) if organization_id else None,
        user_id=current_user.id,
        agent_name=agent_name,
        input={"task": task_input},
        output={"result": result.output, "decision": result.decision},
        status=result.status.value,
        duration_ms=result.duration_ms,
        tokens_used=result.tokens_used,
        model_used=result.model_used,
        error=result.error,
        extra={"confidence": result.decision.confidence if result.decision else None,
               "risk": result.decision.risk_level.value if result.decision else None,
               "files_affected": result.decision.files_affected if result.decision else [],
               "tool_calls": [{"success": t.success, "duration_ms": t.duration_ms} for t in result.tool_calls]},
    )
    db.add(run)

    return {
        "run_id": run_id,
        "agent": agent_name,
        "output": result.output,
        "status": result.status.value,
        "decision": {
            "confidence": result.decision.confidence if result.decision else None,
            "risk": result.decision.risk_level.value if result.decision else None,
            "files_affected": result.decision.files_affected if result.decision else [],
            "reasoning": result.decision.reasoning if result.decision else "",
        } if result.decision else None,
        "duration_ms": result.duration_ms,
        "tokens_used": result.tokens_used,
        "model_used": result.model_used,
        "error": result.error,
    }


@router.post("/pipeline", response_model=dict[str, Any])
async def run_pipeline(
    agents: list[str] = Query(..., min_length=1),
    task_input: str = Query(..., min_length=1, max_length=10000),
    organization_id: Optional[str] = Query(None),
    repository_id: Optional[str] = Query(None),
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run multiple agents sequentially as a pipeline."""
    workflow = AgentWorkflow.sequential(agents, registry)
    context = {"organization_id": organization_id, "repository_id": repository_id}
    final_state = await workflow.run(task_input, context)

    for step in final_state["results"]:
        r = step["result"]
        run = AgentRun(
            organization_id=uuid.UUID(organization_id) if organization_id else None,
            user_id=current_user.id,
            agent_name=step["agent"],
            pipeline_id=final_state["workflow_id"],
            input={"task": task_input, "step": step["step"]},
            output={"result": r["output"]},
            status=r["status"],
            duration_ms=r.get("duration_ms"),
            tokens_used=r.get("tokens_used"),
            error=r.get("error"),
        )
        db.add(run)

    return {
        "workflow_id": final_state["workflow_id"],
        "status": final_state["status"],
        "steps": final_state["results"],
        "errors": final_state["errors"],
    }


@router.get("/runs", response_model=list[dict[str, Any]])
async def list_runs(
    agent_name: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List agent run history."""
    stmt = select(AgentRun).where(AgentRun.user_id == current_user.id)
    if agent_name:
        stmt = stmt.where(AgentRun.agent_name == agent_name)
    stmt = stmt.order_by(AgentRun.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    runs = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "agent": r.agent_name,
            "status": r.status,
            "duration_ms": r.duration_ms,
            "tokens_used": r.tokens_used,
            "model_used": r.model_used,
            "error": r.error,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in runs
    ]


@router.get("/runs/{run_id}", response_model=dict[str, Any])
async def get_run(
    run_id: str,
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed information about a specific agent run."""
    try:
        rid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid run_id")
    result = await db.execute(
        select(AgentRun).where(AgentRun.id == rid, AgentRun.user_id == current_user.id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "id": str(run.id),
        "agent": run.agent_name,
        "pipeline": run.pipeline_id,
        "input": run.input,
        "output": run.output,
        "status": run.status,
        "duration_ms": run.duration_ms,
        "tokens_used": run.tokens_used,
        "model_used": run.model_used,
        "error": run.error,
        "extra": run.extra,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }
