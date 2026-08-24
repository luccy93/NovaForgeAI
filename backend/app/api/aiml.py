"""Volume 58 — AI Governance & MLOps API (NovaForge).

FastAPI APIRouter prefix="/ai" tags=["AI Governance & MLOps"] exposing 45 endpoints
covering model registry, providers, prompts, evaluations, guardrails, policies,
risks, cards, approvals, gateway, monitoring, deployments and provenance.

Auth: _get_current_user + get_db, tenant from user.organization_id fallback to user.id,
authorization via iam.policy_authorizer (try/except allow fallback), audit via
iam.audit_service best-effort, events via core.events.event_bus with idempotency.

Services are imported per-endpoint inside try/except so missing services never crash
the router (degraded path returns 503). All mutating handlers are tenant-scoped,
validate with inline Pydantic, return 404 for tenant-mismatch isolation, 422 for
validation, 409 for conflicts and 403 for policy denials.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import _get_current_user
from app.core.database import get_db
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["AI Governance & MLOps"])

# ── helpers ───────────────────────────────────────────────────────────────

_emitted_keys: set[str] = set()
_deployments: dict[str, dict[str, Any]] = {}


async def _get_tenant(user: User, db: AsyncSession) -> str:
    for attr in ("organization_id", "org_id", "tenant", "tenant_id"):
        v = getattr(user, attr, None)
        if v:
            try:
                s = str(v).strip()
                if s:
                    return s
            except Exception:
                pass
    try:
        from sqlalchemy import text

        result = await db.execute(
            text("SELECT organization_id FROM user_organizations WHERE user_id = :uid LIMIT 1"),
            {"uid": str(user.id)},
        )
        row = result.fetchone()
        if row and row[0]:
            return str(row[0])
        result2 = await db.execute(
            text("SELECT organization_id FROM user_organizations WHERE user_id = :uid LIMIT 1"),
            {"uid": user.id.hex if hasattr(user.id, "hex") else str(user.id)},
        )
        row2 = result2.fetchone()
        if row2 and row2[0]:
            return str(row2[0])
    except Exception as exc:
        logger.debug("tenant lookup failed: %s", exc)
    return str(user.id)


def _check_auth(user: User, tenant: str, permission: str, resource_type: str = "", resource_id: str = "") -> None:
    try:
        from app.iam.policy_authorizer import policy_authorizer  # type: ignore

        ctx: dict[str, Any] = {}
        try:
            role = getattr(user, "role", None)
            if role:
                ctx["role"] = str(role)
        except Exception:
            pass
        decision = policy_authorizer.authorize(
            str(user.id), tenant, permission, resource_type=resource_type, resource_id=resource_id, context=ctx or {"role": "viewer"}
        )
        if not decision.get("allowed", True):
            raise HTTPException(status_code=403, detail=decision.get("reason", "Forbidden"))
    except HTTPException:
        raise
    except Exception as exc:
        logger.debug("policy_authorizer unavailable, allowing %s: %s", permission, exc)


def _audit(actor_id: str, tenant: str, action: str, resource_type: str = "aiml", resource_id: str = "", details: dict | None = None) -> None:
    try:
        from app.iam.audit_service import audit_service  # type: ignore

        try:
            audit_service.log(
                org_id=tenant,
                actor_id=actor_id,
                actor_type="user",
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                result="success",
                details=details or {},
                tenant_id=tenant,
            )
        except TypeError:
            audit_service.log(tenant, actor_id, "user", action, resource_type, resource_id, "success", details or {})
    except Exception as exc:
        logger.debug("audit skipped %s: %s", action, exc)


async def _emit_event(event_type: str, data: dict[str, Any], tenant: str | None = None, actor: str | None = None) -> None:
    try:
        payload = json.dumps(data, sort_keys=True, default=str)
        key_raw = f"{event_type}:{tenant}:{actor}:{payload}"
        idem = hashlib.sha256(key_raw.encode()).hexdigest()
        if idem in _emitted_keys:
            return
        _emitted_keys.add(idem)
        if len(_emitted_keys) > 10000:
            _emitted_keys.clear()
            _emitted_keys.add(idem)
        from app.core.events import Event, EventType, event_bus  # type: ignore

        et = None
        for e in EventType:
            if e.value == event_type or e.name == event_type:
                et = e
                break
        if et is None:
            # try fuzzy governance / aiml matching
            for cand in EventType:
                if event_type.split(".")[-1] in cand.value or event_type.replace(".", "_") in cand.name:
                    et = cand
                    break
            if et is None:
                # fallback mapping for aiml domain
                mapping = {
                    "model": "governance.data.classified",
                    "provider": "governance.policy.violation",
                    "prompt": "governance.data.classified",
                    "evaluation": "governance.policy.violation",
                    "guardrail": "governance.policy.violation",
                    "policy": "governance.policy.violation",
                    "risk": "governance.policy.violation",
                    "card": "governance.evidence.collected",
                    "approval": "governance.request.created",
                    "gateway": "governance.lineage.updated",
                    "monitoring": "governance.policy.violation",
                    "deployment": "delivery.deployment.started",
                    "provenance": "governance.lineage.updated",
                }
                hint = None
                for k, v in mapping.items():
                    if k in event_type:
                        hint = v
                        break
                if hint:
                    for cand in EventType:
                        if cand.value == hint:
                            et = cand
                            break
                if et is None:
                    et = list(EventType)[0]
        evt = Event(event_type=et, data={**data, "_original_event_type": event_type, "_idempotency_key": idem}, source="aiml_api", organization_id=tenant, user_id=actor)
        try:
            await event_bus.publish(evt)
        except Exception:
            try:
                await event_bus.publish_nowait(evt)  # type: ignore
            except Exception:
                pass
    except Exception as exc:
        logger.debug("event emit skipped %s: %s", event_type, exc)


def _parse_uuid(value: str, field: str = "id") -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except Exception:
        raise HTTPException(status_code=422, detail=f"Invalid {field}: {value!r}")


def _model_to_dict(m) -> dict[str, Any]:
    return {
        "id": str(getattr(m, "id", "")),
        "tenant": getattr(m, "tenant", None),
        "provider": getattr(m, "provider", None),
        "name": getattr(m, "name", None),
        "version": getattr(m, "version", None),
        "type": getattr(m, "type", None),
        "capabilities": getattr(m, "capabilities", {}) or {},
        "license": getattr(m, "license", None),
        "region": getattr(m, "region", None),
        "status": getattr(m, "status", None),
        "risk_level": getattr(m, "risk_level", None),
        "owner": getattr(m, "owner", None),
        "model_id": getattr(m, "model_id", None),
        "created_at": getattr(m, "created_at", None).isoformat() if getattr(m, "created_at", None) else None,
        "updated_at": getattr(m, "updated_at", None).isoformat() if getattr(m, "updated_at", None) else None,
    }


def _version_to_dict(v) -> dict[str, Any]:
    return {
        "id": str(getattr(v, "id", "")),
        "model_id": str(getattr(v, "model_id", "")) if getattr(v, "model_id", None) else None,
        "version": getattr(v, "version", None),
        "artifact": getattr(v, "artifact", None),
        "source": getattr(v, "source", None),
        "training_metadata": getattr(v, "training_metadata", {}) or {},
        "evaluation_version": getattr(v, "evaluation_version", None),
        "deployment_version": getattr(v, "deployment_version", None),
        "policy_version": getattr(v, "policy_version", None),
        "provenance": getattr(v, "provenance", {}) or {},
        "immutable": getattr(v, "immutable", None),
        "created_at": getattr(v, "created_at", None).isoformat() if getattr(v, "created_at", None) else None,
    }


def _provider_to_dict(p) -> dict[str, Any]:
    return {
        "id": str(getattr(p, "id", "")),
        "tenant": getattr(p, "tenant", None),
        "provider": getattr(p, "provider", None),
        "display_name": getattr(p, "display_name", None),
        "models": getattr(p, "models", []) or [],
        "regions": getattr(p, "regions", []) or [],
        "pricing": getattr(p, "pricing", {}) or {},
        "data_processing_policy": getattr(p, "data_processing_policy", {}) or {},
        "availability": getattr(p, "availability", None),
        "security_status": getattr(p, "security_status", None),
        "contract_metadata": getattr(p, "contract_metadata", {}) or {},
        "created_at": getattr(p, "created_at", None).isoformat() if getattr(p, "created_at", None) else None,
        "updated_at": getattr(p, "updated_at", None).isoformat() if getattr(p, "updated_at", None) else None,
    }


def _prompt_registry_to_dict(r) -> dict[str, Any]:
    return {
        "id": str(getattr(r, "id", "")),
        "tenant": getattr(r, "tenant", None),
        "prompt_id": getattr(r, "prompt_id", None),
        "name": getattr(r, "name", None),
        "purpose": getattr(r, "purpose", None),
        "classification": getattr(r, "classification", None),
        "model_compatibility": getattr(r, "model_compatibility", []) or [],
        "owner": getattr(r, "owner", None),
        "status": getattr(r, "status", None),
        "created_at": getattr(r, "created_at", None).isoformat() if getattr(r, "created_at", None) else None,
        "updated_at": getattr(r, "updated_at", None).isoformat() if getattr(r, "updated_at", None) else None,
    }


def _prompt_version_to_dict(v) -> dict[str, Any]:
    return {
        "id": str(getattr(v, "id", "")),
        "prompt_id": str(getattr(v, "prompt_id", "")) if getattr(v, "prompt_id", None) else None,
        "version": getattr(v, "version", None),
        "content": getattr(v, "content", None),
        "owner": getattr(v, "owner", None),
        "purpose": getattr(v, "purpose", None),
        "classification": getattr(v, "classification", None),
        "immutable": getattr(v, "immutable", None),
        "created_at": getattr(v, "created_at", None).isoformat() if getattr(v, "created_at", None) else None,
    }


def _suite_to_dict(s) -> dict[str, Any]:
    return {
        "id": str(getattr(s, "id", "")),
        "tenant": getattr(s, "tenant", None),
        "name": getattr(s, "name", None),
        "suite_type": getattr(s, "suite_type", None),
        "dataset_id": getattr(s, "dataset_id", None),
        "dataset_version": getattr(s, "dataset_version", None),
        "config": getattr(s, "config", {}) or {},
        "created_at": getattr(s, "created_at", None).isoformat() if getattr(s, "created_at", None) else None,
    }


def _run_to_dict(r) -> dict[str, Any]:
    return {
        "id": str(getattr(r, "id", "")),
        "tenant": getattr(r, "tenant", None),
        "suite_id": str(getattr(r, "suite_id", "")) if getattr(r, "suite_id", None) else None,
        "model_id": str(getattr(r, "model_id", "")) if getattr(r, "model_id", None) else None,
        "prompt_version_id": str(getattr(r, "prompt_version_id", "")) if getattr(r, "prompt_version_id", None) else None,
        "dataset_version": getattr(r, "dataset_version", None),
        "parameters": getattr(r, "parameters", {}) or {},
        "metrics": getattr(r, "metrics", {}) or {},
        "artifacts": getattr(r, "artifacts", {}) or {},
        "status": getattr(r, "status", None),
        "reproducible_hash": getattr(r, "reproducible_hash", None),
        "created_at": getattr(r, "created_at", None).isoformat() if getattr(r, "created_at", None) else None,
        "updated_at": getattr(r, "updated_at", None).isoformat() if getattr(r, "updated_at", None) else None,
    }


def _guardrail_to_dict(g) -> dict[str, Any]:
    return {
        "id": str(getattr(g, "id", "")),
        "tenant": getattr(g, "tenant", None),
        "name": getattr(g, "name", None),
        "scope": getattr(g, "scope", None),
        "policy": getattr(g, "policy", {}) or {},
        "rate_limit": getattr(g, "rate_limit", None),
        "enabled": getattr(g, "enabled", None),
        "environment": getattr(g, "environment", None),
        "created_at": getattr(g, "created_at", None).isoformat() if getattr(g, "created_at", None) else None,
    }


def _risk_to_dict(r) -> dict[str, Any]:
    return {
        "id": str(getattr(r, "id", "")),
        "tenant": getattr(r, "tenant", None),
        "system": getattr(r, "system", None),
        "model_id": str(getattr(r, "model_id", "")) if getattr(r, "model_id", None) else None,
        "risk_id": getattr(r, "risk_id", None),
        "severity": getattr(r, "severity", None),
        "likelihood": getattr(r, "likelihood", None),
        "impact": getattr(r, "impact", None),
        "owner": getattr(r, "owner", None),
        "mitigation": getattr(r, "mitigation", None),
        "status": getattr(r, "status", None),
        "score": getattr(r, "score", None),
        "created_at": getattr(r, "created_at", None).isoformat() if getattr(r, "created_at", None) else None,
    }


def _card_to_dict(c) -> dict[str, Any]:
    return {
        "id": str(getattr(c, "id", "")),
        "tenant": getattr(c, "tenant", None),
        "model_id": str(getattr(c, "model_id", "")) if getattr(c, "model_id", None) else None,
        "purpose": getattr(c, "purpose", None),
        "capabilities": getattr(c, "capabilities", {}) or {},
        "limitations": getattr(c, "limitations", {}) or {},
        "risk": getattr(c, "risk", None),
        "evaluation_summary": getattr(c, "evaluation_summary", {}) or {},
        "data_policy": getattr(c, "data_policy", None),
        "provider": getattr(c, "provider", None),
        "version": getattr(c, "version", None),
        "approved_environments": getattr(c, "approved_environments", []) or [],
        "created_at": getattr(c, "created_at", None).isoformat() if getattr(c, "created_at", None) else None,
    }


def _system_card_to_dict(c) -> dict[str, Any]:
    return {
        "id": str(getattr(c, "id", "")),
        "tenant": getattr(c, "tenant", None),
        "system": getattr(c, "system", None),
        "purpose": getattr(c, "purpose", None),
        "inputs": getattr(c, "inputs", {}) or {},
        "outputs": getattr(c, "outputs", {}) or {},
        "models": getattr(c, "models", []) or [],
        "tools": getattr(c, "tools", []) or [],
        "permissions": getattr(c, "permissions", []) or [],
        "human_oversight": getattr(c, "human_oversight", None),
        "failure_modes": getattr(c, "failure_modes", []) or [],
        "evaluation": getattr(c, "evaluation", {}) or {},
        "deployment_scope": getattr(c, "deployment_scope", None),
        "created_at": getattr(c, "created_at", None).isoformat() if getattr(c, "created_at", None) else None,
    }


def _approval_to_dict(a) -> dict[str, Any]:
    return {
        "id": str(getattr(a, "id", "")),
        "tenant": getattr(a, "tenant", None),
        "request_type": getattr(a, "request_type", None),
        "model_id": str(getattr(a, "model_id", "")) if getattr(a, "model_id", None) else None,
        "provider": getattr(a, "provider", None),
        "version": getattr(a, "version", None),
        "requested_by": getattr(a, "requested_by", None),
        "approver": getattr(a, "approver", None),
        "status": getattr(a, "status", None),
        "reason": getattr(a, "reason", None),
        "created_at": getattr(a, "created_at", None).isoformat() if getattr(a, "created_at", None) else None,
        "updated_at": getattr(a, "updated_at", None).isoformat() if getattr(a, "updated_at", None) else None,
    }


def _snapshot_to_dict(s) -> dict[str, Any]:
    return {
        "id": str(getattr(s, "id", "")),
        "tenant": getattr(s, "tenant", None),
        "model_id": str(getattr(s, "model_id", "")) if getattr(s, "model_id", None) else None,
        "provider": getattr(s, "provider", None),
        "availability": getattr(s, "availability", None),
        "latency_ms": getattr(s, "latency_ms", None),
        "error_rate": getattr(s, "error_rate", None),
        "token_usage": getattr(s, "token_usage", None),
        "cost": getattr(s, "cost", None),
        "quality": getattr(s, "quality", None),
        "safety": getattr(s, "safety", None),
        "drift": getattr(s, "drift", {}) or {},
        "created_at": getattr(s, "created_at", None).isoformat() if getattr(s, "created_at", None) else None,
    }


# ── Pydantic request bodies ─────────────────────────────────────────────


class ModelCreateRequest(BaseModel):
    provider: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    version: str = Field(..., min_length=1, max_length=64)
    type: str = Field(default="foundation", max_length=32)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    license: Optional[str] = Field(default=None, max_length=64)
    region: Optional[str] = Field(default=None, max_length=32)
    risk_level: str = Field(default="LOW", max_length=16)
    owner: Optional[str] = Field(default=None, max_length=64)


class ModelStatusUpdate(BaseModel):
    status: str = Field(..., description="DRAFT|APPROVED|ACTIVE|DEPRECATED|RETIRED|BLOCKED")


class ModelVersionCreateRequest(BaseModel):
    version: str = Field(..., min_length=1, max_length=64)
    artifact: Optional[str] = Field(default=None, max_length=512)


class ProviderCreateRequest(BaseModel):
    provider: str = Field(..., min_length=1, max_length=64)
    display_name: str = Field(..., min_length=1, max_length=128)
    models: list[str] = Field(default_factory=list)
    regions: list[str] = Field(default_factory=list)
    pricing: dict[str, Any] = Field(default_factory=dict)
    data_processing_policy: dict[str, Any] = Field(default_factory=dict)
    availability: str = Field(default="AVAILABLE", max_length=32)
    security_status: str = Field(default="UNKNOWN", max_length=32)
    contract_metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderAvailabilityUpdate(BaseModel):
    availability: str = Field(..., description="AVAILABLE|DEGRADED|UNAVAILABLE|UNKNOWN|MAINTENANCE")


class PromptCreateRequest(BaseModel):
    prompt_id: str = Field(..., min_length=1, max_length=128)
    name: str = Field(..., min_length=1, max_length=128)
    purpose: Optional[str] = Field(default=None, max_length=256)
    classification: str = Field(default="INTERNAL", max_length=32)
    model_compatibility: list[str] = Field(default_factory=list)
    content: str = Field(..., min_length=1, max_length=200000)
    owner: Optional[str] = Field(default=None, max_length=64)


class PromptVersionCreateRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=200000)
    owner: Optional[str] = Field(default=None, max_length=64)
    purpose: Optional[str] = Field(default=None, max_length=256)
    classification: Optional[str] = Field(default=None, max_length=32)


class SuiteCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    suite_type: str = Field(..., description="benchmark|regression|adversarial|domain|safety|security|golden|functional|quality|compliance")
    dataset_id: Optional[str] = Field(default=None, max_length=128)
    config: dict[str, Any] = Field(default_factory=dict)


class RunCreateRequest(BaseModel):
    suite_id: str = Field(..., min_length=1, max_length=64)
    model_id: Optional[str] = Field(default=None, max_length=64)
    prompt_version_id: Optional[str] = Field(default=None, max_length=64)
    dataset_version: Optional[str] = Field(default=None, max_length=64)
    parameters: dict[str, Any] = Field(default_factory=dict)


class RunCompleteRequest(BaseModel):
    metrics: dict[str, Any] = Field(default_factory=dict)
    artifacts: dict[str, Any] = Field(default_factory=dict)
    status: Optional[str] = Field(default=None, max_length=32)


class GuardrailCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    scope: str = Field(default="input", description="input|output|both")
    policy: dict[str, Any] = Field(default_factory=dict)
    rate_limit: Optional[int] = Field(default=None, ge=0)
    environment: Optional[str] = Field(default=None, max_length=32)


class GuardrailCheckRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=200000)
    classification: str = Field(default="INTERNAL", max_length=32)
    environment: Optional[str] = Field(default=None, max_length=32)


class PolicyCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    policy_type: str = Field(..., min_length=1, max_length=64)
    effect: str = Field(..., description="ALLOW|DENY|REDACT|REQUIRE_APPROVAL|WARN|ANONYMIZE|ESCALATE")
    priority: int = Field(default=0)
    conditions: dict[str, Any] | list[dict[str, Any]] | None = Field(default=None)


class PolicyEvaluateRequest(BaseModel):
    resource: str = Field(..., min_length=1, max_length=256)
    context: dict[str, Any] = Field(default_factory=dict)


class PolicySimulateRequest(BaseModel):
    resource: str = Field(..., min_length=1, max_length=256)
    context: dict[str, Any] = Field(default_factory=dict)


class RiskCreateRequest(BaseModel):
    system: str = Field(..., min_length=1, max_length=128)
    model_id: Optional[str] = Field(default=None, max_length=64)
    risk_id: str = Field(..., min_length=1, max_length=64)
    severity: str = Field(..., description="LOW|MEDIUM|HIGH|CRITICAL")
    likelihood: str = Field(..., description="LOW|MEDIUM|HIGH|CRITICAL etc")
    impact: str = Field(..., description="LOW|MEDIUM|HIGH|CRITICAL etc")
    owner: Optional[str] = Field(default=None, max_length=64)
    mitigation: Optional[str] = Field(default=None)


class RiskAssessRequest(BaseModel):
    status: Optional[str] = Field(default=None, description="OPEN|MITIGATED|ACCEPTED|CLOSED etc — when provided updates status")
    severity: Optional[str] = Field(default=None)
    likelihood: Optional[str] = Field(default=None)
    impact: Optional[str] = Field(default=None)


class ModelCardCreateRequest(BaseModel):
    model_id: str = Field(..., min_length=1, max_length=64, description="ai_model_registry.id UUID")
    purpose: Optional[str] = Field(default=None)
    capabilities: dict[str, Any] | list[str] | None = Field(default=None)
    limitations: dict[str, Any] | list[str] | str | None = Field(default=None)
    risk: Optional[str] = Field(default=None, max_length=16)
    evaluation_summary: dict[str, Any] = Field(default_factory=dict)
    data_policy: Optional[str] = Field(default=None, max_length=64)
    provider: Optional[str] = Field(default=None, max_length=64)
    version: Optional[str] = Field(default=None, max_length=64)
    approved_environments: list[str] = Field(default_factory=list)


class SystemCardCreateRequest(BaseModel):
    system: str = Field(..., min_length=1, max_length=128)
    purpose: Optional[str] = Field(default=None)
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    models: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    human_oversight: Optional[str] = Field(default=None)
    failure_modes: list[str] = Field(default_factory=list)
    evaluation: dict[str, Any] = Field(default_factory=dict)
    deployment_scope: Optional[str] = Field(default=None, max_length=64)


class ApprovalCreateRequest(BaseModel):
    request_type: str = Field(..., min_length=1, max_length=32)
    model_id: Optional[str] = Field(default=None, max_length=64)
    provider: Optional[str] = Field(default=None, max_length=64)
    version: Optional[str] = Field(default=None, max_length=64)
    reason: Optional[str] = Field(default=None)


class ApprovalDecideRequest(BaseModel):
    approver: str = Field(..., min_length=1, max_length=64)
    decision: str = Field(..., description="approved|rejected|approve|reject|allow|deny")


class GatewayInvokeRequest(BaseModel):
    model_id: str = Field(..., min_length=1, max_length=64)
    prompt: str = Field(..., min_length=1, max_length=200000)
    data_classification: str = Field(default="INTERNAL", max_length=32)
    purpose: Optional[str] = Field(default=None, max_length=128)


class GatewayRouteRequest(BaseModel):
    purpose: Optional[str] = Field(default=None, max_length=128)
    data_classification: str = Field(default="INTERNAL", max_length=32)
    model_hint: Optional[str] = Field(default=None, max_length=128)
    provider_hint: Optional[str] = Field(default=None, max_length=64)
    region_hint: Optional[str] = Field(default=None, max_length=32)
    budget: Optional[float] = Field(default=None, ge=0)
    policy_context: dict[str, Any] = Field(default_factory=dict)


class SnapshotCreateRequest(BaseModel):
    model_id: Optional[str] = Field(default=None, max_length=64)
    provider: Optional[str] = Field(default=None, max_length=64)
    availability: Optional[str] = Field(default=None, max_length=32)
    latency_ms: Optional[float] = Field(default=None, ge=0)
    error_rate: Optional[float] = Field(default=None, ge=0, le=1)
    token_usage: Optional[int] = Field(default=None, ge=0)
    cost: Optional[float] = Field(default=None, ge=0)
    quality: Optional[float] = Field(default=None, ge=0, le=1)
    safety: Optional[float] = Field(default=None, ge=0, le=1)
    drift: dict[str, Any] = Field(default_factory=dict)


class DriftRequest(BaseModel):
    model_id: Optional[str] = Field(default=None, max_length=64)
    window: int = Field(default=100, ge=2, le=1000)


class DeploymentCreateRequest(BaseModel):
    model_id: str = Field(..., min_length=1, max_length=64, description="ai_model_registry.id UUID")
    version: Optional[str] = Field(default=None, max_length=64)
    environment: str = Field(default="production", max_length=32)
    provider: Optional[str] = Field(default=None, max_length=64)
    approved_by: Optional[str] = Field(default=None, max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── Models ─────────────────────────────────────────────────────────────────


@router.post("/models", status_code=status.HTTP_201_CREATED)
async def create_model(body: ModelCreateRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _check_auth(current_user, tenant, "aiml.model.create", "ai_model_registry", body.name)
    try:
        from app.aiml.registry import registry_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"registry service unavailable: {exc}")
    try:
        row = await registry_service.register_model(
            db, tenant=tenant, provider=body.provider, name=body.name, version=body.version,
            type=body.type, capabilities=body.capabilities, license=body.license,
            region=body.region, risk_level=body.risk_level, owner=body.owner or str(current_user.id),
        )
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        msg = str(e)
        # map core exceptions via string to preserve behavior without hard import
        if "tenant is required" in msg or "provider is required" in msg or "invalid" in msg.lower():
            raise HTTPException(status_code=422, detail=msg)
        if "already exists" in msg.lower() or "conflict" in msg.lower() or "silently replace" in msg.lower():
            raise HTTPException(status_code=409, detail=msg)
        raise HTTPException(status_code=422, detail=msg)
    await _emit_event("governance.data.classified", {"model_id": str(getattr(row, "id", "")), "tenant": tenant, "provider": body.provider, "name": body.name, "version": body.version}, tenant, str(current_user.id))
    _audit(str(current_user.id), tenant, "aiml.model.created", "ai_model_registry", str(getattr(row, "id", "")), {"provider": body.provider, "name": body.name, "version": body.version})
    return _model_to_dict(row)


@router.get("/models")
async def list_models(
    provider: Optional[str] = Query(None),
    name: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    type: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant = await _get_tenant(current_user, db)
    try:
        from app.aiml.registry import registry_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"registry service unavailable: {exc}")
    filters: dict[str, Any] = {}
    if provider:
        filters["provider"] = provider
    if name:
        filters["name"] = name
    if status_filter:
        filters["status"] = status_filter
    if type:
        filters["type"] = type
    if region:
        filters["region"] = region
    try:
        rows = await registry_service.list_models(db, tenant=tenant, filters=filters)
        return [_model_to_dict(r) for r in rows]
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/models/{model_id}")
async def get_model(model_id: str, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _parse_uuid(model_id, "model_id")
    try:
        from app.aiml.registry import registry_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"registry service unavailable: {exc}")
    try:
        row = await registry_service.get_model(db, tenant=tenant, model_id=model_id)
        if not row:
            raise HTTPException(status_code=404, detail="Model not found")
        return _model_to_dict(row)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.put("/models/{model_id}/status")
async def update_model_status(model_id: str, body: ModelStatusUpdate, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _parse_uuid(model_id, "model_id")
    _check_auth(current_user, tenant, "aiml.model.update", "ai_model_registry", model_id)
    try:
        from app.aiml.registry import registry_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"registry service unavailable: {exc}")
    # tenant isolation: verify model belongs to tenant
    try:
        existing = await registry_service.get_model(db, tenant=tenant, model_id=model_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Model not found")
    except HTTPException:
        raise
    except Exception:
        pass
    try:
        row = await registry_service.update_status(db, model_id=model_id, status=body.status)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        if "invalid status" in msg.lower():
            raise HTTPException(status_code=422, detail=msg)
        raise HTTPException(status_code=422, detail=msg)
    await _emit_event("governance.policy.violation", {"model_id": model_id, "status": body.status, "tenant": tenant}, tenant, str(current_user.id))
    _audit(str(current_user.id), tenant, "aiml.model.status_updated", "ai_model_registry", model_id, {"status": body.status})
    return _model_to_dict(row)


@router.post("/models/{model_id}/versions", status_code=status.HTTP_201_CREATED)
async def create_model_version(model_id: str, body: ModelVersionCreateRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _parse_uuid(model_id, "model_id")
    _check_auth(current_user, tenant, "aiml.model.create_version", "ai_model_registry", model_id)
    try:
        from app.aiml.registry import registry_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"registry service unavailable: {exc}")
    # isolation check
    try:
        existing = await registry_service.get_model(db, tenant=tenant, model_id=model_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Model not found")
    except HTTPException:
        raise
    except Exception:
        pass
    try:
        row = await registry_service.create_version(db, model_id=model_id, version=body.version, artifact=body.artifact)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        if "already exists" in msg.lower() or "immutable" in msg.lower() or "conflict" in msg.lower():
            raise HTTPException(status_code=409, detail=msg)
        raise HTTPException(status_code=422, detail=msg)
    await _emit_event("governance.lineage.updated", {"model_id": model_id, "version": body.version, "tenant": tenant}, tenant, str(current_user.id))
    _audit(str(current_user.id), tenant, "aiml.model.version_created", "ai_model_versions", str(getattr(row, "id", "")), {"model_id": model_id, "version": body.version})
    return _version_to_dict(row)


@router.get("/models/{model_id}/versions")
async def list_model_versions(model_id: str, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _parse_uuid(model_id, "model_id")
    try:
        from app.aiml.registry import registry_service  # type: ignore
        from app.aiml.models import AIModelVersion  # type: ignore
        from sqlalchemy import select
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"registry service unavailable: {exc}")
    # isolation
    try:
        existing = await registry_service.get_model(db, tenant=tenant, model_id=model_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Model not found")
    except HTTPException:
        raise
    except Exception:
        pass
    try:
        from sqlalchemy import select as _sel

        stmt = _sel(AIModelVersion).where(AIModelVersion.model_id == _parse_uuid(model_id, "model_id")).order_by(AIModelVersion.created_at.asc())
        result = await db.execute(stmt)
        rows = list(result.scalars().all())
        return [_version_to_dict(r) for r in rows]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/models/{model_id}/approve")
async def approve_model(model_id: str, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _parse_uuid(model_id, "model_id")
    _check_auth(current_user, tenant, "aiml.model.approve", "ai_model_registry", model_id)
    try:
        from app.aiml.registry import registry_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"registry service unavailable: {exc}")
    try:
        existing = await registry_service.get_model(db, tenant=tenant, model_id=model_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Model not found")
    except HTTPException:
        raise
    except Exception:
        pass
    try:
        row = await registry_service.update_status(db, model_id=model_id, status="APPROVED")
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=422, detail=msg)
    await _emit_event("governance.request.created", {"model_id": model_id, "action": "approved", "tenant": tenant}, tenant, str(current_user.id))
    _audit(str(current_user.id), tenant, "aiml.model.approved", "ai_model_registry", model_id, {"status": "APPROVED"})
    return _model_to_dict(row)


@router.post("/models/{model_id}/block")
async def block_model(model_id: str, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _parse_uuid(model_id, "model_id")
    _check_auth(current_user, tenant, "aiml.model.block", "ai_model_registry", model_id)
    try:
        from app.aiml.registry import registry_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"registry service unavailable: {exc}")
    try:
        existing = await registry_service.get_model(db, tenant=tenant, model_id=model_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Model not found")
    except HTTPException:
        raise
    except Exception:
        pass
    try:
        row = await registry_service.block(db, model_id=model_id)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=422, detail=msg)
    await _emit_event("governance.policy.violation", {"model_id": model_id, "action": "blocked", "tenant": tenant}, tenant, str(current_user.id))
    _audit(str(current_user.id), tenant, "aiml.model.blocked", "ai_model_registry", model_id, {"status": "BLOCKED"})
    return _model_to_dict(row)


# ── Providers ──────────────────────────────────────────────────────────────


@router.post("/providers", status_code=status.HTTP_201_CREATED)
async def create_provider(body: ProviderCreateRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _check_auth(current_user, tenant, "aiml.provider.create", "ai_provider_registry", body.provider)
    try:
        from app.aiml.providers import provider_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"provider service unavailable: {exc}")
    try:
        row = await provider_service.register_provider(
            db, tenant=tenant, provider=body.provider, display_name=body.display_name,
            models=body.models, regions=body.regions, pricing=body.pricing,
            data_processing_policy=body.data_processing_policy, availability=body.availability,
            security_status=body.security_status, contract_metadata=body.contract_metadata,
        )
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        msg = str(e)
        if "already registered" in msg.lower() or "conflict" in msg.lower():
            raise HTTPException(status_code=409, detail=msg)
        if "invalid" in msg.lower() or "required" in msg.lower():
            raise HTTPException(status_code=422, detail=msg)
        raise HTTPException(status_code=422, detail=msg)
    await _emit_event("governance.policy.violation", {"provider": body.provider, "tenant": tenant, "action": "registered"}, tenant, str(current_user.id))
    _audit(str(current_user.id), tenant, "aiml.provider.created", "ai_provider_registry", str(getattr(row, "id", "")), {"provider": body.provider})
    return _provider_to_dict(row)


@router.get("/providers")
async def list_providers(
    provider: Optional[str] = Query(None),
    availability: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant = await _get_tenant(current_user, db)
    try:
        from app.aiml.providers import provider_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"provider service unavailable: {exc}")
    filters: dict[str, Any] = {}
    if provider:
        filters["provider"] = provider
    if availability:
        filters["availability"] = availability
    if region:
        filters["region"] = region
    try:
        rows = await provider_service.list_providers(db, tenant=tenant, filters=filters)
        return [_provider_to_dict(r) for r in rows]
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/providers/{provider}")
async def get_provider(provider: str, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    try:
        from app.aiml.providers import provider_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"provider service unavailable: {exc}")
    try:
        row = await provider_service.get_provider(db, tenant=tenant, provider=provider)
        if not row:
            raise HTTPException(status_code=404, detail="Provider not found")
        return _provider_to_dict(row)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.put("/providers/{provider}/availability")
async def update_provider_availability(provider: str, body: ProviderAvailabilityUpdate, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _check_auth(current_user, tenant, "aiml.provider.update", "ai_provider_registry", provider)
    try:
        from app.aiml.providers import provider_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"provider service unavailable: {exc}")
    try:
        row = await provider_service.update_availability(db, tenant=tenant, provider=provider, availability=body.availability)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=422, detail=msg)
    await _emit_event("governance.policy.violation", {"provider": provider, "availability": body.availability, "tenant": tenant}, tenant, str(current_user.id))
    _audit(str(current_user.id), tenant, "aiml.provider.availability_updated", "ai_provider_registry", provider, {"availability": body.availability})
    return _provider_to_dict(row)


# ── Prompts ────────────────────────────────────────────────────────────────


@router.post("/prompts", status_code=status.HTTP_201_CREATED)
async def create_prompt(body: PromptCreateRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _check_auth(current_user, tenant, "aiml.prompt.create", "ai_prompt_registry", body.prompt_id)
    try:
        from app.aiml.prompts import prompt_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"prompt service unavailable: {exc}")
    try:
        result = await prompt_service.register_prompt(
            db, tenant=tenant, prompt_id=body.prompt_id, name=body.name, purpose=body.purpose,
            classification=body.classification, model_compatibility=body.model_compatibility,
            content=body.content, owner=body.owner or str(current_user.id),
        )
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        msg = str(e)
        if "already exists" in msg.lower() or "conflict" in msg.lower():
            raise HTTPException(status_code=409, detail=msg)
        raise HTTPException(status_code=422, detail=msg)
    # result contains registry and version
    reg = result.get("registry") if isinstance(result, dict) else result
    ver = result.get("version") if isinstance(result, dict) else None
    await _emit_event("governance.data.classified", {"prompt_id": body.prompt_id, "tenant": tenant, "classification": body.classification}, tenant, str(current_user.id))
    _audit(str(current_user.id), tenant, "aiml.prompt.created", "ai_prompt_registry", str(getattr(reg, "id", body.prompt_id)), {"prompt_id": body.prompt_id})
    out = _prompt_registry_to_dict(reg)
    if ver is not None:
        out["version"] = _prompt_version_to_dict(ver)
        out["latest_version"] = _prompt_version_to_dict(ver)
    return out


@router.get("/prompts")
async def list_prompts(current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    try:
        from app.aiml.prompts import prompt_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"prompt service unavailable: {exc}")
    try:
        rows = await prompt_service.list_prompts(db, tenant=tenant)
        return [_prompt_registry_to_dict(r) for r in rows]
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/prompts/{prompt_id}")
async def get_prompt(prompt_id: str, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    try:
        from app.aiml.prompts import prompt_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"prompt service unavailable: {exc}")
    try:
        snap = await prompt_service.get_prompt(db, tenant=tenant, prompt_id=prompt_id)
        if not snap:
            raise HTTPException(status_code=404, detail="Prompt not found")
        reg = snap.get("registry") if isinstance(snap, dict) else snap
        ver = snap.get("version") if isinstance(snap, dict) else None
        versions = snap.get("versions") if isinstance(snap, dict) else []
        out = _prompt_registry_to_dict(reg)
        if ver is not None:
            out["version"] = _prompt_version_to_dict(ver)
        if versions:
            out["versions"] = [_prompt_version_to_dict(v) for v in versions]
        latest = snap.get("latest_version") if isinstance(snap, dict) else None
        if latest is not None:
            out["latest_version"] = _prompt_version_to_dict(latest)
        return out
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/prompts/{prompt_id}/versions", status_code=status.HTTP_201_CREATED)
async def create_prompt_version(prompt_id: str, body: PromptVersionCreateRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _check_auth(current_user, tenant, "aiml.prompt.create_version", "ai_prompt_registry", prompt_id)
    try:
        from app.aiml.prompts import prompt_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"prompt service unavailable: {exc}")
    # isolation check — ensure prompt belongs to tenant
    try:
        snap = await prompt_service.get_prompt(db, tenant=tenant, prompt_id=prompt_id)
        if not snap:
            raise HTTPException(status_code=404, detail="Prompt not found")
    except HTTPException:
        raise
    except Exception:
        pass
    try:
        row = await prompt_service.create_version(db, prompt_id=prompt_id, content=body.content, owner=body.owner or str(current_user.id), purpose=body.purpose, classification=body.classification)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        if "already exists" in msg.lower() or "immutable" in msg.lower() or "conflict" in msg.lower():
            raise HTTPException(status_code=409, detail=msg)
        raise HTTPException(status_code=422, detail=msg)
    await _emit_event("governance.data.classified", {"prompt_id": prompt_id, "tenant": tenant, "action": "version_created"}, tenant, str(current_user.id))
    _audit(str(current_user.id), tenant, "aiml.prompt.version_created", "ai_prompt_versions", str(getattr(row, "id", "")), {"prompt_id": prompt_id})
    return _prompt_version_to_dict(row)


# ── Evaluations ────────────────────────────────────────────────────────────


@router.post("/evaluations/suites", status_code=status.HTTP_201_CREATED)
async def create_evaluation_suite(body: SuiteCreateRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _check_auth(current_user, tenant, "aiml.evaluation.create", "ai_evaluation_suites", body.name)
    try:
        from app.aiml.evaluations import evaluation_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"evaluation service unavailable: {exc}")
    try:
        row = await evaluation_service.create_suite(db, tenant=tenant, name=body.name, suite_type=body.suite_type, dataset_id=body.dataset_id, config=body.config)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    await _emit_event("governance.evidence.collected", {"suite_id": str(getattr(row, "id", "")), "tenant": tenant, "suite_type": body.suite_type}, tenant, str(current_user.id))
    _audit(str(current_user.id), tenant, "aiml.evaluation.suite_created", "ai_evaluation_suites", str(getattr(row, "id", "")), {"suite_type": body.suite_type})
    return _suite_to_dict(row)


@router.post("/evaluations/runs", status_code=status.HTTP_201_CREATED)
async def create_evaluation_run(body: RunCreateRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _check_auth(current_user, tenant, "aiml.evaluation.create", "ai_evaluation_runs", body.suite_id)
    try:
        from app.aiml.evaluations import evaluation_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"evaluation service unavailable: {exc}")
    try:
        row = await evaluation_service.create_run(
            db, tenant=tenant, suite_id=body.suite_id, model_id=body.model_id,
            prompt_version_id=body.prompt_version_id, dataset_version=body.dataset_version, parameters=body.parameters,
        )
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=422, detail=msg)
    await _emit_event("governance.evidence.collected", {"run_id": str(getattr(row, "id", "")), "suite_id": body.suite_id, "tenant": tenant}, tenant, str(current_user.id))
    _audit(str(current_user.id), tenant, "aiml.evaluation.run_created", "ai_evaluation_runs", str(getattr(row, "id", "")), {"suite_id": body.suite_id})
    return _run_to_dict(row)


@router.get("/evaluations/runs/{run_id}")
async def get_evaluation_run(run_id: str, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _parse_uuid(run_id, "run_id")
    try:
        from app.aiml.evaluations import evaluation_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"evaluation service unavailable: {exc}")
    try:
        row = await evaluation_service.get_run(db, tenant=tenant, run_id=run_id)
        if not row:
            raise HTTPException(status_code=404, detail="Evaluation run not found")
        return _run_to_dict(row)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/evaluations/runs/{run_id}/complete")
async def complete_evaluation_run(run_id: str, body: RunCompleteRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _parse_uuid(run_id, "run_id")
    _check_auth(current_user, tenant, "aiml.evaluation.complete", "ai_evaluation_runs", run_id)
    try:
        from app.aiml.evaluations import evaluation_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"evaluation service unavailable: {exc}")
    # isolation check via get_run
    try:
        existing = await evaluation_service.get_run(db, tenant=tenant, run_id=run_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Evaluation run not found")
    except HTTPException:
        raise
    except Exception:
        pass
    try:
        row = await evaluation_service.complete_run(db, run_id=run_id, metrics=body.metrics, artifacts=body.artifacts, status=body.status)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=422, detail=msg)
    await _emit_event("governance.policy.violation", {"run_id": run_id, "tenant": tenant, "action": "completed"}, tenant, str(current_user.id))
    _audit(str(current_user.id), tenant, "aiml.evaluation.run_completed", "ai_evaluation_runs", run_id, {"metrics": list(body.metrics.keys())})
    return _run_to_dict(row)


@router.get("/evaluations/compare")
async def compare_evaluations(
    candidate_run_id: str = Query(..., description="Candidate run UUID"),
    baseline_run_id: str = Query(..., description="Baseline run UUID"),
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant = await _get_tenant(current_user, db)
    _parse_uuid(candidate_run_id, "candidate_run_id")
    _parse_uuid(baseline_run_id, "baseline_run_id")
    try:
        from app.aiml.evaluations import evaluation_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"evaluation service unavailable: {exc}")
    try:
        result = await evaluation_service.compare_regression(db, candidate_run_id=candidate_run_id, baseline_run_id=baseline_run_id)
        # ensure tenant isolation was enforced by service; double-check tenant field
        if result.get("tenant") and result["tenant"] != tenant:
            raise HTTPException(status_code=404, detail="Evaluation runs not found for tenant")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        if "different tenants" in msg.lower() or "isolation" in msg.lower():
            raise HTTPException(status_code=403, detail=msg)
        raise HTTPException(status_code=422, detail=msg)


# ── Guardrails ─────────────────────────────────────────────────────────────


@router.post("/guardrails", status_code=status.HTTP_201_CREATED)
async def create_guardrail(body: GuardrailCreateRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _check_auth(current_user, tenant, "aiml.guardrail.create", "ai_guardrails", body.name)
    try:
        from app.aiml.guardrails import guardrail_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"guardrail service unavailable: {exc}")
    try:
        row = await guardrail_service.create_guardrail(db, tenant=tenant, name=body.name, scope=body.scope, policy=body.policy, rate_limit=body.rate_limit, environment=body.environment)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    await _emit_event("governance.policy.violation", {"guardrail_id": str(getattr(row, "id", "")), "name": body.name, "tenant": tenant, "scope": body.scope}, tenant, str(current_user.id))
    _audit(str(current_user.id), tenant, "aiml.guardrail.created", "ai_guardrails", str(getattr(row, "id", "")), {"name": body.name, "scope": body.scope})
    return _guardrail_to_dict(row)


@router.get("/guardrails")
async def list_guardrails(
    scope: Optional[str] = Query(None),
    environment: Optional[str] = Query(None),
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant = await _get_tenant(current_user, db)
    try:
        from app.aiml.guardrails import guardrail_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"guardrail service unavailable: {exc}")
    try:
        rows = await guardrail_service.list_guardrails(db, tenant=tenant, scope=scope, environment=environment)
        return [_guardrail_to_dict(r) for r in rows]
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/guardrails/check-input")
async def check_guardrail_input(body: GuardrailCheckRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    try:
        from app.aiml.guardrails import guardrail_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"guardrail service unavailable: {exc}")
    try:
        result = await guardrail_service.check_input(db, tenant=tenant, content=body.content, classification=body.classification, environment=body.environment)
        return result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/guardrails/check-output")
async def check_guardrail_output(body: GuardrailCheckRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    try:
        from app.aiml.guardrails import guardrail_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"guardrail service unavailable: {exc}")
    try:
        result = await guardrail_service.check_output(db, tenant=tenant, content=body.content, classification=body.classification, environment=body.environment)
        return result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ── Policies ───────────────────────────────────────────────────────────────


@router.post("/policies", status_code=status.HTTP_201_CREATED)
async def create_policy(body: PolicyCreateRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _check_auth(current_user, tenant, "aiml.policy.create", "ai_policy", body.name)
    try:
        from app.aiml.policies import policy_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"policy service unavailable: {exc}")
    try:
        result = await policy_service.create_policy(db, tenant=tenant, name=body.name, policy_type=body.policy_type, effect=body.effect, priority=body.priority, conditions=body.conditions)
        await db.commit()
        await _emit_event("governance.policy.violation", {"policy_id": result.get("id"), "tenant": tenant, "name": body.name, "effect": body.effect}, tenant, str(current_user.id))
        _audit(str(current_user.id), tenant, "aiml.policy.created", "ai_policy", str(result.get("id", "")), {"name": body.name, "effect": body.effect})
        return result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        msg = str(e)
        if "invalid" in msg.lower() or "required" in msg.lower():
            raise HTTPException(status_code=422, detail=msg)
        raise HTTPException(status_code=422, detail=msg)


@router.post("/policies/evaluate")
async def evaluate_policy(body: PolicyEvaluateRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    try:
        from app.aiml.policies import policy_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"policy service unavailable: {exc}")
    try:
        result = await policy_service.evaluate(db, tenant=tenant, resource=body.resource, context=body.context)
        if result.get("decision") == "DENY":
            await _emit_event("governance.policy.violation", {"resource": body.resource, "decision": "DENY", "tenant": tenant}, tenant, str(current_user.id))
        return result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/policies/simulate")
async def simulate_policy(body: PolicySimulateRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    try:
        from app.aiml.policies import policy_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"policy service unavailable: {exc}")
    try:
        result = await policy_service.simulate(db, tenant=tenant, resource=body.resource, context=body.context)
        return result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/policies/decisions")
async def list_policy_decisions(
    resource: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant = await _get_tenant(current_user, db)
    # PolicyEngine stores decisions implicitly via evaluation; surface recent policies as decisions source
    try:
        from app.governance.policy_engine import PolicyEngine  # type: ignore
        from app.aiml.policies import _engine_storage_dir  # type: ignore

        for stor in (_engine_storage_dir(tenant), "policy_engine_data"):
            try:
                eng = PolicyEngine(storage_dir=stor)  # type: ignore
                policies = eng.list_policies(org_id=tenant)  # type: ignore
                out = []
                for p in policies or []:
                    if resource and resource not in getattr(p, "name", "") and resource != getattr(p, "id", ""):
                        continue
                    out.append({
                        "id": getattr(p, "id", None),
                        "name": getattr(p, "name", None),
                        "type": getattr(getattr(p, "type", None), "value", str(getattr(p, "type", ""))),
                        "effect": getattr(getattr(p, "effect", None), "value", str(getattr(p, "effect", ""))),
                        "priority": getattr(p, "priority", None),
                        "status": getattr(getattr(p, "status", None), "value", str(getattr(p, "status", ""))),
                        "version": getattr(p, "version", None),
                    })
                    if len(out) >= limit:
                        break
                return {"tenant": tenant, "count": len(out), "decisions": out, "resource": resource}
            except Exception:
                continue
        return {"tenant": tenant, "count": 0, "decisions": [], "resource": resource}
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"policy engine unavailable: {exc}")
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))


# ── Risks ──────────────────────────────────────────────────────────────────


@router.post("/risks", status_code=status.HTTP_201_CREATED)
async def create_risk(body: RiskCreateRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _check_auth(current_user, tenant, "aiml.risk.create", "ai_risk_records", body.system)
    try:
        from app.aiml.risk import risk_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"risk service unavailable: {exc}")
    try:
        row = await risk_service.create_risk(
            db, tenant=tenant, system=body.system, model_id=body.model_id, risk_id=body.risk_id,
            severity=body.severity, likelihood=body.likelihood, impact=body.impact,
            owner=body.owner or str(current_user.id), mitigation=body.mitigation,
        )
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    await _emit_event("governance.policy.violation", {"risk_id": body.risk_id, "system": body.system, "tenant": tenant, "severity": body.severity}, tenant, str(current_user.id))
    _audit(str(current_user.id), tenant, "aiml.risk.created", "ai_risk_records", str(getattr(row, "id", "")), {"risk_id": body.risk_id, "system": body.system})
    return _risk_to_dict(row)


@router.get("/risks")
async def list_risks(
    system: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant = await _get_tenant(current_user, db)
    try:
        from app.aiml.risk import risk_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"risk service unavailable: {exc}")
    filters: dict[str, Any] = {}
    if system:
        filters["system"] = system
    if severity:
        filters["severity"] = severity
    if status_filter:
        filters["status"] = status_filter
    try:
        rows = await risk_service.list_risks(db, tenant=tenant, filters=filters)
        return [_risk_to_dict(r) for r in rows]
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/risks/{risk_id}/assess")
async def assess_risk(risk_id: str, body: RiskAssessRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _check_auth(current_user, tenant, "aiml.risk.assess", "ai_risk_records", risk_id)
    try:
        from app.aiml.risk import risk_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"risk service unavailable: {exc}")
    try:
        # fetch risk tenant-scoped
        existing = await risk_service.get_risk(db, tenant=tenant, risk_id=risk_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Risk not found")
        # if status provided, update status
        if body.status and body.status.strip():
            row = await risk_service.update_status(db, tenant=tenant, risk_id=risk_id, status=body.status)
            await db.commit()
        else:
            row = existing
        # calculate governance score (pure heuristic, never legal conclusion)
        try:
            score = await risk_service.calculate_score(row)
        except Exception:
            score = getattr(row, "score", None)
        # if severity/likelihood/impact overrides provided, recompute score advisory
        if body.severity or body.likelihood or body.impact:
            advisory: dict[str, Any] = {
                "severity": body.severity or getattr(row, "severity", None),
                "likelihood": body.likelihood or getattr(row, "likelihood", None),
                "impact": body.impact or getattr(row, "impact", None),
            }
            try:
                alt_score = await risk_service.calculate_score(advisory)
                return {**_risk_to_dict(row), "assessed_score": alt_score, "advisory": advisory, "note": "score is a governance heuristic — not a legal conclusion"}
            except Exception:
                pass
        return {**_risk_to_dict(row), "assessed_score": score, "note": "score is a governance heuristic — not a legal conclusion"}
    except HTTPException:
        raise
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=422, detail=msg)


# ── Model / System Cards ───────────────────────────────────────────────────


@router.post("/model-cards", status_code=status.HTTP_201_CREATED)
async def create_model_card(body: ModelCardCreateRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _parse_uuid(body.model_id, "model_id")
    _check_auth(current_user, tenant, "aiml.card.create", "ai_model_cards", body.model_id)
    try:
        from app.aiml.cards import card_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"card service unavailable: {exc}")
    try:
        row = await card_service.create_model_card(
            db, tenant=tenant, model_id=body.model_id, purpose=body.purpose, capabilities=body.capabilities,
            limitations=body.limitations, risk=body.risk, evaluation_summary=body.evaluation_summary,
            data_policy=body.data_policy, provider=body.provider, version=body.version,
            approved_environments=body.approved_environments,
        )
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=422, detail=msg)
    await _emit_event("governance.evidence.collected", {"card_id": str(getattr(row, "id", "")), "model_id": body.model_id, "tenant": tenant}, tenant, str(current_user.id))
    _audit(str(current_user.id), tenant, "aiml.model_card.created", "ai_model_cards", str(getattr(row, "id", "")), {"model_id": body.model_id})
    return _card_to_dict(row)


@router.get("/model-cards/{model_id}")
async def get_model_cards(model_id: str, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    # model_id here is the registry model PK; list cards for that model tenant-scoped
    try:
        from app.aiml.cards import card_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"card service unavailable: {exc}")
    try:
        # try get single card if model_id looks like card id first, else list by model
        try:
            _parse_uuid(model_id, "model_id")
        except HTTPException:
            raise
        # attempt list by model_id filter
        rows = await card_service.list_model_cards(db, tenant=tenant, model_id=model_id)
        if rows:
            return [_card_to_dict(r) for r in rows]
        # fallback single card fetch by card PK
        single = await card_service.get_model_card(db, tenant=tenant, card_id=model_id)
        if single:
            return _card_to_dict(single)
        # also support provenance-style model_id that may be provider/name:version? — require uuid so 404
        raise HTTPException(status_code=404, detail="Model card not found")
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/system-cards", status_code=status.HTTP_201_CREATED)
async def create_system_card(body: SystemCardCreateRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _check_auth(current_user, tenant, "aiml.system_card.create", "ai_system_cards", body.system)
    try:
        from app.aiml.cards import card_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"card service unavailable: {exc}")
    try:
        row = await card_service.create_system_card(
            db, tenant=tenant, system=body.system, purpose=body.purpose, inputs=body.inputs, outputs=body.outputs,
            models=body.models, tools=body.tools, permissions=body.permissions,
            human_oversight=body.human_oversight, failure_modes=body.failure_modes,
            evaluation=body.evaluation, deployment_scope=body.deployment_scope,
        )
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    await _emit_event("governance.evidence.collected", {"system": body.system, "tenant": tenant, "card_id": str(getattr(row, "id", ""))}, tenant, str(current_user.id))
    _audit(str(current_user.id), tenant, "aiml.system_card.created", "ai_system_cards", str(getattr(row, "id", "")), {"system": body.system})
    return _system_card_to_dict(row)


@router.get("/system-cards/{system}")
async def get_system_cards(system: str, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    try:
        from app.aiml.cards import card_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"card service unavailable: {exc}")
    try:
        # system param may be card PK uuid or system name — try pk first
        try:
            pk = uuid.UUID(system)
            row = await card_service.get_system_card(db, tenant=tenant, card_id=system)
            if row:
                return _system_card_to_dict(row)
        except Exception:
            pass
        rows = await card_service.list_system_cards(db, tenant=tenant, system=system)
        if rows:
            return [_system_card_to_dict(r) for r in rows]
        raise HTTPException(status_code=404, detail="System card not found")
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ── Approvals ──────────────────────────────────────────────────────────────


@router.post("/approvals", status_code=status.HTTP_201_CREATED)
async def create_approval(body: ApprovalCreateRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _check_auth(current_user, tenant, "aiml.approval.create", "ai_approval_requests", body.request_type)
    try:
        from app.aiml.approvals import approval_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"approval service unavailable: {exc}")
    try:
        row = await approval_service.request_approval(
            db, tenant=tenant, request_type=body.request_type, model_id=body.model_id,
            provider=body.provider, version=body.version, requested_by=str(current_user.id), reason=body.reason,
        )
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        msg = str(e)
        if "already exists" in msg.lower() or "pending approval" in msg.lower() or "conflict" in msg.lower():
            raise HTTPException(status_code=409, detail=msg)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=422, detail=msg)
    await _emit_event("governance.request.created", {"approval_id": str(getattr(row, "id", "")), "tenant": tenant, "request_type": body.request_type}, tenant, str(current_user.id))
    _audit(str(current_user.id), tenant, "aiml.approval.requested", "ai_approval_requests", str(getattr(row, "id", "")), {"request_type": body.request_type})
    return _approval_to_dict(row)


@router.post("/approvals/{approval_id}/decide")
async def decide_approval(approval_id: str, body: ApprovalDecideRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _parse_uuid(approval_id, "approval_id")
    _check_auth(current_user, tenant, "aiml.approval.decide", "ai_approval_requests", approval_id)
    try:
        from app.aiml.approvals import approval_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"approval service unavailable: {exc}")
    # isolation: verify belongs to tenant
    try:
        existing = await approval_service.get_approval(db, tenant=tenant, approval_id=approval_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Approval not found")
    except HTTPException:
        raise
    except Exception:
        pass
    try:
        row = await approval_service.approve(db, approval_id=approval_id, approver=body.approver, decision=body.decision)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        if "already decided" in msg.lower() or "conflict" in msg.lower() or "reuse" in msg.lower():
            raise HTTPException(status_code=409, detail=msg)
        raise HTTPException(status_code=422, detail=msg)
    await _emit_event("governance.request.created", {"approval_id": approval_id, "decision": body.decision, "tenant": tenant}, tenant, str(current_user.id))
    _audit(str(current_user.id), tenant, f"aiml.approval.{body.decision}", "ai_approval_requests", approval_id, {"decision": body.decision})
    return _approval_to_dict(row)


# ── Gateway ────────────────────────────────────────────────────────────────


@router.post("/gateway/invoke")
async def gateway_invoke(body: GatewayInvokeRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _check_auth(current_user, tenant, "aiml.gateway.invoke", "ai_model_registry", body.model_id)
    try:
        from app.aiml.gateway import gateway_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"gateway service unavailable: {exc}")
    try:
        result = await gateway_service.invoke(db, tenant=tenant, actor=str(current_user.id), model_id=body.model_id, prompt=body.prompt, data_classification=body.data_classification, purpose=body.purpose)
        await _emit_event("governance.lineage.updated", {"model_id": body.model_id, "tenant": tenant, "action": "invoke", "classification": body.data_classification}, tenant, str(current_user.id))
        _audit(str(current_user.id), tenant, "aiml.gateway.invoked", "ai_gateway", body.model_id, {"classification": body.data_classification})
        return result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        if "unapproved" in msg.lower() or "never deploy" in msg.lower():
            raise HTTPException(status_code=403, detail=msg)
        if "unavailable" in msg.lower():
            raise HTTPException(status_code=503, detail=msg)
        if "policy" in msg.lower() and ("deny" in msg.lower() or "blocked" in msg.lower() or "require" in msg.lower()):
            raise HTTPException(status_code=403, detail=msg)
        if "guardrail" in msg.lower():
            raise HTTPException(status_code=403, detail=msg)
        if "fail-closed" in msg.lower():
            raise HTTPException(status_code=403, detail=msg)
        raise HTTPException(status_code=422, detail=msg)


@router.post("/gateway/route")
async def gateway_route(body: GatewayRouteRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    try:
        from app.aiml.gateway import gateway_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"gateway service unavailable: {exc}")
    try:
        result = await gateway_service.route(
            db, tenant=tenant, purpose=body.purpose, data_classification=body.data_classification,
            model_hint=body.model_hint, provider_hint=body.provider_hint, region_hint=body.region_hint,
            budget=body.budget, policy_context=body.policy_context,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        msg = str(e)
        if "fail-closed" in msg.lower() or "no authorized" in msg.lower() or "denied" in msg.lower() or "blocked" in msg.lower():
            raise HTTPException(status_code=403, detail=msg)
        raise HTTPException(status_code=422, detail=msg)


# ── Monitoring ─────────────────────────────────────────────────────────────


@router.post("/monitoring/snapshots", status_code=status.HTTP_201_CREATED)
async def create_monitoring_snapshot(body: SnapshotCreateRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _check_auth(current_user, tenant, "aiml.monitoring.create", "ai_monitoring_snapshots", body.model_id or "")
    try:
        from app.aiml.monitoring import monitoring_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"monitoring service unavailable: {exc}")
    try:
        row = await monitoring_service.record_snapshot(
            db, tenant=tenant, model_id=body.model_id, provider=body.provider, availability=body.availability,
            latency_ms=body.latency_ms, error_rate=body.error_rate, token_usage=body.token_usage,
            cost=body.cost, quality=body.quality, safety=body.safety, drift=body.drift,
        )
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    await _emit_event("governance.policy.violation", {"snapshot_id": str(getattr(row, "id", "")), "model_id": body.model_id, "tenant": tenant}, tenant, str(current_user.id))
    _audit(str(current_user.id), tenant, "aiml.monitoring.snapshot_recorded", "ai_monitoring_snapshots", str(getattr(row, "id", "")), {"model_id": body.model_id})
    return _snapshot_to_dict(row)


@router.get("/monitoring/{model_id}")
async def get_monitoring(model_id: str, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    try:
        from app.aiml.monitoring import monitoring_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"monitoring service unavailable: {exc}")
    try:
        rows = await monitoring_service.get_snapshots(db, tenant=tenant, model_id=model_id, limit=100)
        return [_snapshot_to_dict(r) for r in rows]
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/monitoring/drift")
async def check_monitoring_drift(body: DriftRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    try:
        from app.aiml.monitoring import monitoring_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"monitoring service unavailable: {exc}")
    try:
        result = await monitoring_service.detect_drift(db, tenant=tenant, model_id=body.model_id, window=body.window)
        return result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ── Deployments ────────────────────────────────────────────────────────────


@router.post("/deployments", status_code=status.HTTP_201_CREATED)
async def create_deployment(body: DeploymentCreateRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _parse_uuid(body.model_id, "model_id")
    _check_auth(current_user, tenant, "aiml.deployment.create", "ai_model_registry", body.model_id)
    try:
        from app.aiml.registry import registry_service  # type: ignore
        from app.aiml.monitoring import monitoring_service  # type: ignore
    except Exception:
        # allow deployment even if monitoring not available — log but proceed
        monitoring_service = None  # type: ignore
        try:
            from app.aiml.registry import registry_service  # type: ignore
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"registry service unavailable: {exc}")
    # verify model tenant-scoped
    try:
        existing = await registry_service.get_model(db, tenant=tenant, model_id=body.model_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Model not found")
        if existing.status not in ("APPROVED", "ACTIVE"):
            raise HTTPException(status_code=403, detail=f"never deploy unapproved model: status={existing.status} — requires APPROVED/ACTIVE")
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    # approve/active gate: ensure provider available when known
    try:
        from app.aiml.providers import provider_service  # type: ignore

        prov = await provider_service.get_provider(db, tenant=tenant, provider=existing.provider)
        if prov is not None and getattr(prov, "availability", "AVAILABLE") != "AVAILABLE":
            raise HTTPException(status_code=503, detail=f"provider '{existing.provider}' unavailable (availability={prov.availability})")
    except HTTPException:
        raise
    except Exception:
        pass
    deployment_id = str(uuid.uuid4())
    record: dict[str, Any] = {
        "id": deployment_id,
        "tenant": tenant,
        "model_id": body.model_id,
        "version": body.version or getattr(existing, "version", None),
        "environment": body.environment,
        "provider": body.provider or getattr(existing, "provider", None),
        "approved_by": body.approved_by or str(current_user.id),
        "requested_by": str(current_user.id),
        "status": "deployed",
        "metadata": body.metadata or {},
        "model_name": getattr(existing, "name", None),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _deployments[deployment_id] = record
    # also transition model to ACTIVE if it was APPROVED
    try:
        if getattr(existing, "status", "") == "APPROVED":
            await registry_service.update_status(db, model_id=body.model_id, status="ACTIVE")
            await db.commit()
    except Exception:
        pass
    # record monitoring snapshot best-effort
    try:
        if monitoring_service is not None:
            await monitoring_service.record_snapshot(db, tenant=tenant, model_id=body.model_id, provider=record["provider"], availability="AVAILABLE", latency_ms=0, error_rate=0, token_usage=0, cost=0, drift={"deployment_id": deployment_id, "environment": body.environment})
            await db.commit()
    except Exception:
        pass
    await _emit_event("delivery.deployment.started", {"deployment_id": deployment_id, "model_id": body.model_id, "tenant": tenant, "environment": body.environment}, tenant, str(current_user.id))
    _audit(str(current_user.id), tenant, "aiml.deployment.created", "ai_deployment", deployment_id, {"model_id": body.model_id, "environment": body.environment})
    return record


@router.post("/deployments/{deployment_id}/rollback")
async def rollback_deployment(deployment_id: str, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _parse_uuid(deployment_id, "deployment_id")
    _check_auth(current_user, tenant, "aiml.deployment.rollback", "ai_deployment", deployment_id)
    record = _deployments.get(deployment_id)
    if not record or record.get("tenant") != tenant:
        raise HTTPException(status_code=404, detail="Deployment not found")
    if record.get("status") == "rolled_back":
        raise HTTPException(status_code=409, detail="Deployment already rolled back")
    # transition model if possible — deprecate deployed model
    try:
        from app.aiml.registry import registry_service  # type: ignore

        model_id = record.get("model_id")
        if model_id:
            try:
                existing = await registry_service.get_model(db, tenant=tenant, model_id=model_id)
                if existing is not None:
                    # rollback means deprecate current deployment, but keep model for audit
                    await registry_service.update_status(db, model_id=model_id, status="DEPRECATED")
                    await db.commit()
            except Exception:
                pass
    except Exception:
        pass
    record["status"] = "rolled_back"
    record["rolled_back_at"] = datetime.now(timezone.utc).isoformat()
    record["rolled_back_by"] = str(current_user.id)
    _deployments[deployment_id] = record
    await _emit_event("delivery.deployment.rollback", {"deployment_id": deployment_id, "model_id": record.get("model_id"), "tenant": tenant}, tenant, str(current_user.id))
    _audit(str(current_user.id), tenant, "aiml.deployment.rollback", "ai_deployment", deployment_id, {"model_id": record.get("model_id")})
    return record


# ── Provenance ─────────────────────────────────────────────────────────────


@router.get("/provenance/{model_id}")
async def get_provenance(model_id: str, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _parse_uuid(model_id, "model_id")
    try:
        from app.aiml.provenance import provenance_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"provenance service unavailable: {exc}")
    try:
        result = await provenance_service.get_provenance(db, model_id=model_id)
        # tenant isolation: provenance service infers tenant from registry; verify matches
        if result.get("tenant") and result["tenant"] != tenant:
            raise HTTPException(status_code=404, detail="Model not found")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=422, detail=msg)

