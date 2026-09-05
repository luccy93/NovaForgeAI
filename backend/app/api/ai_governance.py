"""AI Governance API (Volumes 36-37).

Surface: asset registry, model/prompt/agent/tool governance, policy engine,
drift/safety monitoring, kill switches, circuit breakers, human oversight,
dependency graph, release management, and audit events.

All endpoints require authentication. Mutating operational endpoints
require the admin_all permission; read-only endpoints require any authenticated user.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any
from datetime import datetime, timezone

from app.api.auth import _get_current_user, require_permission
from app.core.authorization import Permission
from app.core.database import get_db
from app.governance.compliance_frameworks import ComplianceManager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["AI Governance"])


# ─── Request/Response Models ────────────────────────────────────────────---

class AIAssetIn(BaseModel):
    id: str
    name: str
    type: str = "model"  # model, prompt, agent, tool
    version: str = ""
    owner: str = ""
    provider: str = ""
    capabilities: str = ""
    risk: str = "medium"
    status: str = "pending"
    environment: str = "development"
    data_policy: str = ""
    evaluation_status: str = "pending"
    approval_status: str = "pending"
    tags: str = ""
    dependencies: str = ""


class AIPromptIn(AIAssetIn):
    pass


class AIAgentIn(AIAssetIn):
    autonomy_level: str = "medium"
    tool_access: str = ""


class AIToolIn(AIAssetIn):
    integration_type: str = "http"
    autonomy_level: str = "medium"


class AIPolicyIn(BaseModel):
    id: str
    name: str
    version: str = "1.0.0"
    policy_type: str = "general"  # model, prompt, agent, tool, data, provider, region, autonomy, action
    effect: str = "allow"
    severity: str = "medium"
    priority: int = 0
    conditions: str = ""
    tags: str = ""
    status: str = "active"


class AIExceptionIn(BaseModel):
    id: str
    name: str
    policy_id: str = ""
    asset_id: str = ""
    asset_type: str = "model"  # model, prompt, agent, tool
    justification: str = ""
    expires_at: Optional[str] = None
    granted_by: str = ""
    granted_at: Optional[str] = None
    conditions: str = ""


class AIGovernanceReviewIn(BaseModel):
    id: str
    asset_id: str
    asset_type: str = "model"
    reviewer: str = ""
    review_type: str = "regular"
    criteria: str = ""
    status: str = "pending"
    risk_level: str = "medium"
    findings: str = ""
    recommendations: str = ""
    expires_at: Optional[str] = None


class AILifecycleEventIn(BaseModel):
    id: str
    asset_id: str
    asset_type: str = "model"
    event_type: str = "release"
    timestamp: Optional[str] = None
    actor: str = "system"
    details: str = ""
    compliance_status: str = ""


# ─── Asset Registry Endpoints ──────────────────────────────────────────────

@router.post("/assets", status_code=201)
async def create_ai_asset(
    body: AIAssetIn,
    current_user: Any = Depends(_get_current_user),
    db=Depends(get_db),
) -> dict:
    """Register a new AI asset."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    asset = manager.register_ai_asset(body.dict())
    return asset


@router.get("/assets")
async def list_ai_assets(
    asset_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """List AI assets, optionally filtered by type and status."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    assets = manager.list_ai_assets(org_id=current_user.org_id, asset_type=asset_type, status=status)
    return {"total": len(assets), "items": assets}


@router.get("/assets/{asset_id}")
async def get_ai_asset(
    asset_id: str,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Get a specific AI asset by ID."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    asset = manager.get_ai_asset(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail=f"AI asset {asset_id} not found")
    return asset


@router.put("/assets/{asset_id}")
async def update_ai_asset(
    asset_id: str,
    updates: dict,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Update an AI asset."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    asset = manager.update_ai_asset(asset_id, updates)
    if not asset:
        raise HTTPException(status_code=404, detail=f"AI asset {asset_id} not found")
    return asset


# ─── Model Risk Classification ─────────────────────────────────────────────

@router.post("/assets/{asset_id}/classify-risk")
async def classify_model_risk(
    asset_id: str,
    risk_factors: dict,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Classify a model's risk based on configurable factors."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    result = manager.classify_model_risk(asset_id, risk_factors)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/assets/{asset_id}/approve")
async def approve_ai_asset(
    asset_id: str,
    approver: str = Query(...),
    reason: str = Query(...),
    expires_at: Optional[str] = Query(None),
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Approve an AI asset through the governance gate."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    result = manager.approve_ai_asset(asset_id, approver, reason, expires_at)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/assets/{asset_id}/restrict")
async def restrict_ai_asset(
    asset_id: str,
    reason: str = Query(...),
    restricted_by: str = Query(...),
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Restrict an AI asset (e.g., pending review, policy violation)."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    result = manager.restrict_ai_asset(asset_id, reason, restricted_by)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/assets/{asset_id}/retire")
async def retire_ai_asset(
    asset_id: str,
    replacement_id: Optional[str] = Query(None),
    reason: str = Query(""),
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Retire an AI asset."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    result = manager.retire_ai_asset(asset_id, replacement_id, reason)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ─── Prompt Governance ────────────────────────────────────────────────────

@router.post("/prompts", status_code=201)
async def create_ai_prompt(
    body: AIPromptIn,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Register a new AI prompt."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    prompt = manager.register_ai_prompt(body.dict())
    return prompt


@router.get("/prompts")
async def list_ai_prompts(
    status: Optional[str] = Query(None),
    risk_level: Optional[str] = Query(None),
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """List AI prompts, optionally filtered by status and risk level."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    prompts = manager.list_ai_prompts(org_id=current_user.org_id, status=status, risk_level=risk_level)
    return {"total": len(prompts), "items": prompts}


@router.get("/prompts/{prompt_id}")
async def get_ai_prompt(
    prompt_id: str,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Get a specific AI prompt by ID."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    prompt = manager.get_ai_prompt(prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail=f"AI prompt {prompt_id} not found")
    return prompt


@router.put("/prompts/{prompt_id}")
async def update_ai_prompt(
    prompt_id: str,
    updates: dict,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Update an AI prompt."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    prompt = manager.update_ai_prompt(prompt_id, updates)
    if not prompt:
        raise HTTPException(status_code=404, detail=f"AI prompt {prompt_id} not found")
    return prompt


@router.post("/prompts/{prompt_id}/evaluate")
async def evaluate_ai_prompt(
    prompt_id: str,
    evaluation_criteria: dict,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Evaluate an AI prompt against governance criteria."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    result = manager.evaluate_ai_prompt(prompt_id, evaluation_criteria)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ─── Agent Governance ─────────────────────────────────────────────────────

@router.post("/agents", status_code=201)
async def create_ai_agent(
    body: AIAgentIn,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Register a new AI agent."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    agent = manager.register_ai_agent(body.dict())
    return agent


@router.get("/agents")
async def list_ai_agents(
    status: Optional[str] = Query(None),
    risk_level: Optional[str] = Query(None),
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """List AI agents, optionally filtered by status and risk level."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    agents = manager.list_ai_agents(org_id=current_user.org_id, status=status, risk_level=risk_level)
    return {"total": len(agents), "items": agents}


@router.get("/agents/{agent_id}")
async def get_ai_agent(
    agent_id: str,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Get a specific AI agent by ID."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    agent = manager.get_ai_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"AI agent {agent_id} not found")
    return agent


@router.put("/agents/{agent_id}")
async def update_ai_agent(
    agent_id: str,
    updates: dict,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Update an AI agent."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    agent = manager.update_ai_agent(agent_id, updates)
    if not agent:
        raise HTTPException(status_code=404, detail=f"AI agent {agent_id} not found")
    return agent


@router.post("/agents/{agent_id}/evaluate")
async def evaluate_ai_agent(
    agent_id: str,
    evaluation_criteria: dict,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Evaluate an AI agent against governance criteria."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    result = manager.evaluate_ai_agent(agent_id, evaluation_criteria)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ─── Tool Governance ───────────────────────────────────────────────────────

@router.post("/tools", status_code=201)
async def create_ai_tool(
    body: AIToolIn,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Register a new AI tool."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    tool = manager.register_ai_tool(body.dict())
    return tool


@router.get("/tools")
async def list_ai_tools(
    status: Optional[str] = Query(None),
    risk_level: Optional[str] = Query(None),
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """List AI tools, optionally filtered by status and risk level."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    tools = manager.list_ai_tools(org_id=current_user.org_id, status=status, risk_level=risk_level)
    return {"total": len(tools), "items": tools}


@router.get("/tools/{tool_id}")
async def get_ai_tool(
    tool_id: str,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Get a specific AI tool by ID."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    tool = manager.get_ai_tool(tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail=f"AI tool {tool_id} not found")
    return tool


@router.put("/tools/{tool_id}")
async def update_ai_tool(
    tool_id: str,
    updates: dict,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Update an AI tool."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    tool = manager.update_ai_tool(tool_id, updates)
    if not tool:
        raise HTTPException(status_code=404, detail=f"AI tool {tool_id} not found")
    return tool


@router.post("/tools/{tool_id}/evaluate")
async def evaluate_ai_tool(
    tool_id: str,
    evaluation_criteria: dict,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Evaluate an AI tool against governance criteria."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    result = manager.evaluate_ai_tool(tool_id, evaluation_criteria)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ─── AI Policy Registry ────────────────────────────────────────────────────

@router.post("/policies", status_code=201)
async def create_ai_policy(
    body: AIPolicyIn,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Register a new AI policy."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    policy = manager.register_ai_policy(body.dict())
    return policy


@router.get("/policies")
async def list_ai_policies(
    policy_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """List AI policies, optionally filtered by type and status."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    policies = manager.list_ai_policies(org_id=current_user.org_id, policy_type=policy_type, status=status)
    return {"total": len(policies), "items": policies}


@router.get("/policies/{policy_id}")
async def get_ai_policy(
    policy_id: str,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Get a specific AI policy by ID."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    policy = manager.get_ai_policy(policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail=f"AI policy {policy_id} not found")
    return policy


@router.put("/policies/{policy_id}")
async def update_ai_policy(
    policy_id: str,
    updates: dict,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Update an AI policy."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    policy = manager.update_ai_policy(policy_id, updates)
    if not policy:
        raise HTTPException(status_code=404, detail=f"AI policy {policy_id} not found")
    return policy


@router.post("/policies/{policy_id}/evaluate")
async def evaluate_ai_policy_decision(
    policy_id: str,
    asset_id: str = Query(...),
    asset_type: str = Query("model"),
    context: dict = Body(default={}),
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Evaluate an AI policy decision against an asset in context."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    result = manager.evaluate_ai_policy_decision(policy_id, asset_id, context)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ─── AI Exception Management ───────────────────────────────────────────────

@router.post("/exceptions", status_code=201)
async def create_ai_exception(
    body: AIExceptionIn,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Create an AI exception for policy compliance."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    exception = manager.create_ai_exception(body.dict())
    return exception


@router.get("/exceptions")
async def list_ai_exceptions(
    policy_id: Optional[str] = Query(None),
    asset_type: Optional[str] = Query(None),
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """List AI exceptions, optionally filtered by policy and asset type."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    exceptions = manager.list_ai_exceptions(org_id=current_user.org_id, policy_id=policy_id, asset_type=asset_type)
    return {"total": len(exceptions), "items": exceptions}


# ─── AI Governance Reviews ────────────────────────────────────────────────

@router.post("/reviews", status_code=201)
async def create_ai_governance_review(
    body: AIGovernanceReviewIn,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Create an AI governance review."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    review = manager.create_ai_governance_review(body.dict())
    return review


@router.get("/reviews")
async def list_ai_governance_reviews(
    asset_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """List AI governance reviews, optionally filtered by asset type and status."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    reviews = manager.list_ai_governance_reviews(org_id=current_user.org_id, asset_type=asset_type, status=status)
    return {"total": len(reviews), "items": reviews}


# ─── AI Lifecycle Events ───────────────────────────────────────────────────

@router.post("/lifecycle-events", status_code=201)
async def create_ai_lifecycle_event(
    body: AILifecycleEventIn,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Create an AI lifecycle event."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    event = manager.create_ai_lifecycle_event(body.dict())
    return event


@router.get("/lifecycle-events")
async def list_ai_lifecycle_events(
    asset_type: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """List AI lifecycle events, optionally filtered by asset type and event type."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    events = manager.list_ai_lifecycle_events(org_id=current_user.org_id, asset_type=asset_type, event_type=event_type)
    return {"total": len(events), "items": events}


# ─── AI Security Integration ───────────────────────────────────────────────

@router.get("/assets/{asset_id}/security")
async def check_ai_security(
    asset_id: str,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Check AI asset security status."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    result = manager.check_ai_security(asset_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/assets/{asset_id}/health")
async def check_ai_health(
    asset_id: str,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Check overall AI asset health including performance, safety, and compliance."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    result = manager.check_ai_health(asset_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ─── AI Monitoring, Drift Detection ────────────────────────────────────────

@router.post("/assets/{asset_id}/record-evaluation")
async def record_ai_evaluation(
    asset_id: str,
    evaluation: dict,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Record an AI evaluation result for an asset."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    result = manager.record_ai_evaluation(asset_id, evaluation)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/assets/{asset_id}/drift")
async def check_ai_drift(
    asset_id: str,
    window_days: int = Query(30),
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Check for drift in an AI asset's performance over a window."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    result = manager.check_ai_drift(asset_id, window_days=window_days)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/assets/{asset_id}/safety")
async def check_ai_safety(
    asset_id: str,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Check AI asset safety status and return safety advisory."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    result = manager.check_ai_safety(asset_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ─── Kill Switch, Circuit Breaker, Human Oversight ─────────────────────────

@router.post("/assets/{asset_id}/kill-switch/activate")
async def activate_kill_switch(
    asset_id: str,
    activated_by: str = Query(...),
    reason: str = Query(...),
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Activate a kill switch on an AI asset (immediate shutdown)."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    result = manager.activate_kill_switch(asset_id, activated_by, reason)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/assets/{asset_id}/kill-switch/deactivate")
async def deactivate_kill_switch(
    asset_id: str,
    deactivated_by: str = Query(...),
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Deactivate a kill switch on an AI asset."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    result = manager.deactivate_kill_switch(asset_id, deactivated_by)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/assets/{asset_id}/kill-switch")
async def check_kill_switch(
    asset_id: str,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Check if a kill switch is active on an AI asset."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    result = manager.check_kill_switch(asset_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/assets/{asset_id}/circuit-breaker/activate")
async def activate_circuit_breaker(
    asset_id: str,
    activated_by: str = Query(...),
    reason: str = Query(...),
    reset_condition: str = Query("manual"),
    reset_threshold: int = Query(5),
    reset_counter: int = Query(0),
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Activate a circuit breaker on an AI asset (prevent further executions)."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    result = manager.activate_circuit_breaker(asset_id, activated_by, reason, reset_condition, reset_threshold, reset_counter)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/assets/{asset_id}/circuit-breaker/deactivate")
async def deactivate_circuit_breaker(
    asset_id: str,
    deactivated_by: str = Query(...),
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Deactivate a circuit breaker on an AI asset."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    result = manager.deactivate_circuit_breaker(asset_id, deactivated_by)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/assets/{asset_id}/circuit-breaker")
async def check_circuit_breaker(
    asset_id: str,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Check circuit breaker status on an AI asset."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    result = manager.check_circuit_breaker(asset_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/assets/{asset_id}/human-oversight/decision")
async def human_oversight_decision(
    asset_id: str,
    decision: str = Query(...),
    decided_by: str = Query(...),
    reason: str = Query(...),
    action: str = Query("monitor"),
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Record a human oversight decision on an AI asset."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    result = manager.human_oversight_decision(asset_id, decision, decided_by, reason, action)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/assets/{asset_id}/human-oversight")
async def check_human_oversight(
    asset_id: str,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Check human oversight status on an AI asset."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    result = manager.check_human_oversight(asset_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ─── AI Inventory, Dependency Graph, Release Management ────────────────────

@router.post("/dependencies", status_code=201)
async def register_ai_dependency(
    dependency: dict,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Register an AI asset dependency."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    result = manager.register_ai_dependency(dependency)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/dependencies")
async def list_ai_dependencies(
    asset_id: str = Query(...),
    direction: Optional[str] = Query(None),
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """List AI dependencies for an asset."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    deps = manager.list_ai_dependencies(asset_id, direction=direction)
    return {"total": len(deps), "items": deps}


@router.post("/releases", status_code=201)
async def register_ai_release(
    release: dict,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Register an AI asset release/version."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    result = manager.register_ai_release(release)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/releases")
async def list_ai_releases(
    asset_id: str = Query(...),
    status: Optional[str] = Query(None),
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """List AI releases for an asset."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    releases = manager.list_ai_releases(asset_id, status=status)
    return {"total": len(releases), "items": releases}


@router.post("/releases/{release_id}/compatibility")
async def check_release_compatibility(
    asset_id: str,
    target_release_id: str = Query(...),
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Check if a target release is compatible with an asset's current state."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    result = manager.check_ai_release_compatibility(asset_id, target_release_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/inventory/summary")
async def get_ai_inventory_summary(
    org_id: str = Query(...),
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Get a summary of all AI assets for an organization."""
    from app.governance.compliance_frameworks import ComplianceManager
    manager = ComplianceManager(org_id=current_user.org_id)
    summary = manager.get_ai_inventory_summary(org_id=org_id)
    return summary