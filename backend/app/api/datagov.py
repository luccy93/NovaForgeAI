"""Volume 57 — Data Governance API (NovaForge).

FastAPI APIRouter prefix="/governance" tags=["Data Governance"] exposing 50+ endpoints
covering assets, classification, lineage, retention, DSR, exports, processors, consents,
policies, controls, legal holds, exceptions, DLP, risk and dashboard.

Auth: _get_current_user + get_db, tenant from user.organization_id fallback to user.id,
authorization via iam.policy_authorizer (try/except allow fallback), audit via
iam.audit_service best-effort, events via core.events.event_bus with idempotency.

Services are imported per-endpoint inside try/except so missing services never crash
the router (degraded path returns 503 or fallback query).
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.auth import _get_current_user
from app.core.database import get_db
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/governance", tags=["Data Governance"])

# ── helpers ────────────────────────────────────────────────────────────────

_emitted_keys: set[str] = set()

async def _get_tenant(user: User, db: AsyncSession) -> str:
    for attr in ("organization_id", "org_id", "tenant", "tenant_id"):
        v = getattr(user, attr, None)
        if v:
            try:
                return str(v).strip()
            except Exception:
                pass
    try:
        from sqlalchemy import text
        result = await db.execute(text("SELECT organization_id FROM user_organizations WHERE user_id = :uid LIMIT 1"), {"uid": str(user.id)})
        row = result.fetchone()
        if row and row[0]:
            return str(row[0])
        result2 = await db.execute(text("SELECT organization_id FROM user_organizations WHERE user_id = :uid LIMIT 1"), {"uid": user.id.hex if hasattr(user.id, "hex") else str(user.id)})
        row2 = result2.fetchone()
        if row2 and row2[0]:
            return str(row2[0])
    except Exception as exc:
        logger.debug("tenant lookup failed: %s", exc)
    return str(user.id)


def _check_auth(user: User, tenant: str, permission: str, resource_type: str = "", resource_id: str = "") -> None:
    try:
        from app.iam.policy_authorizer import policy_authorizer  # type: ignore
        ctx = {}
        try:
            role = getattr(user, "role", None)
            if role:
                ctx["role"] = str(role)
        except Exception:
            pass
        decision = policy_authorizer.authorize(str(user.id), tenant, permission, resource_type=resource_type, resource_id=resource_id, context=ctx or {"role": "viewer"})
        if not decision.get("allowed", True):
            raise HTTPException(status_code=403, detail=decision.get("reason", "Forbidden"))
    except HTTPException:
        raise
    except Exception as exc:
        logger.debug("policy_authorizer unavailable, allowing %s: %s", permission, exc)


def _audit(actor_id: str, tenant: str, action: str, resource_type: str = "governance", resource_id: str = "", details: dict | None = None) -> None:
    try:
        from app.iam.audit_service import audit_service  # type: ignore
        try:
            audit_service.log(org_id=tenant, actor_id=actor_id, actor_type="user", action=action, resource_type=resource_type, resource_id=resource_id, result="success", details=details or {}, tenant_id=tenant)
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
        # keep set bounded
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
            # map governance events to closest EventType, fallback to first
            fallback_map = {
                "governance.asset.discovered": "governance.lineage.updated" if hasattr(EventType, "governance_lineage_updated") else None,
                "governance.data.classified": None,
                "governance.lineage.updated": None,
                "governance.retention.violation": None,
                "governance.request.created": None,
                "governance.export.completed": None,
                "governance.policy.violation": None,
                "governance.control.status_changed": None,
                "governance.evidence.collected": None,
                "governance.legal_hold.created": None,
                "governance.exception.expired": None,
                "governance.dlp.violation": None,
                "data.redacted": None,
            }
            # use generic governance fallback or first enum
            if hasattr(EventType, "governance_asset_discovered"):
                # not standard, search any governance prefix
                for cand in EventType:
                    if "governance" in cand.value:
                        et = cand
                        break
            if et is None:
                et = list(EventType)[0]
        evt = Event(event_type=et, data={**data, "_original_event_type": event_type, "_idempotency_key": idem}, source="governance_api", organization_id=tenant, user_id=actor)
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


def _asset_to_dict(a) -> dict[str, Any]:
    return {
        "id": str(getattr(a, "id", "")),
        "asset_id": getattr(a, "asset_id", None),
        "tenant": getattr(a, "tenant", None),
        "workspace": getattr(a, "workspace", None),
        "project": getattr(a, "project", None),
        "resource": getattr(a, "resource", None),
        "type": getattr(a, "type", None),
        "owner": getattr(a, "owner", None),
        "classification": getattr(a, "classification", None),
        "source": getattr(a, "source", None),
        "location": getattr(a, "location", None),
        "retention_policy": getattr(a, "retention_policy", None),
        "sensitivity": getattr(a, "sensitivity", None),
        "metadata_json": getattr(a, "metadata_json", {}) or {},
        "created_at": getattr(a, "created_at", None).isoformat() if getattr(a, "created_at", None) else None,
        "updated_at": getattr(a, "updated_at", None).isoformat() if getattr(a, "updated_at", None) else None,
    }


def _class_to_dict(c) -> dict[str, Any]:
    return {
        "id": str(getattr(c, "id", "")),
        "asset_id": getattr(c, "asset_id", None),
        "tenant": getattr(c, "tenant", None),
        "level": getattr(c, "level", None),
        "source": getattr(c, "source", None),
        "confidence": getattr(c, "confidence", None),
        "advisory": getattr(c, "advisory", None),
        "evidence": getattr(c, "evidence", {}) or {},
        "classified_by": getattr(c, "classified_by", None),
        "created_at": getattr(c, "created_at", None).isoformat() if getattr(c, "created_at", None) else None,
    }


def _lineage_to_dict(e) -> dict[str, Any]:
    return {
        "id": str(getattr(e, "id", "")),
        "tenant": getattr(e, "tenant", None),
        "source_asset": getattr(e, "source_asset", None),
        "target_asset": getattr(e, "target_asset", None),
        "transformation": getattr(e, "transformation", None),
        "evidence": getattr(e, "evidence", None),
        "stage": getattr(e, "stage", None),
        "metadata_json": getattr(e, "metadata_json", {}) or {},
        "created_at": getattr(e, "created_at", None).isoformat() if getattr(e, "created_at", None) else None,
    }


def _retention_to_dict(p) -> dict[str, Any]:
    return {
        "id": str(getattr(p, "id", "")),
        "tenant": getattr(p, "tenant", None),
        "resource": getattr(p, "resource", None),
        "classification": getattr(p, "classification", None),
        "data_type": getattr(p, "data_type", None),
        "environment": getattr(p, "environment", None),
        "retention_days": getattr(p, "retention_days", None),
        "action": getattr(p, "action", None),
        "state": getattr(p, "state", None),
        "created_at": getattr(p, "created_at", None).isoformat() if getattr(p, "created_at", None) else None,
    }


def _request_to_dict(r) -> dict[str, Any]:
    return {
        "id": str(getattr(r, "id", "")),
        "tenant": getattr(r, "tenant", None),
        "request_type": getattr(r, "request_type", None),
        "subject": getattr(r, "subject", None),
        "scope": getattr(r, "scope", {}) or {},
        "verification_status": getattr(r, "verification_status", None),
        "approval_status": getattr(r, "approval_status", None),
        "systems": getattr(r, "systems", []) or [],
        "completion": getattr(r, "completion", {}) or {},
        "exceptions": getattr(r, "exceptions", []) or [],
        "requested_by": getattr(r, "requested_by", None),
        "created_at": getattr(r, "created_at", None).isoformat() if getattr(r, "created_at", None) else None,
        "updated_at": getattr(r, "updated_at", None).isoformat() if getattr(r, "updated_at", None) else None,
    }


def _export_to_dict(e) -> dict[str, Any]:
    return {
        "id": str(getattr(e, "id", "")),
        "tenant": getattr(e, "tenant", None),
        "request_id": str(getattr(e, "request_id", "")) if getattr(e, "request_id", None) else None,
        "requester": getattr(e, "requester", None),
        "scope": getattr(e, "scope", {}) or {},
        "data_sources": getattr(e, "data_sources", []) or [],
        "format": getattr(e, "format", None),
        "expires_at": getattr(e, "expires_at", None).isoformat() if getattr(e, "expires_at", None) else None,
        "status": getattr(e, "status", None),
        "created_at": getattr(e, "created_at", None).isoformat() if getattr(e, "created_at", None) else None,
    }


def _processor_to_dict(p) -> dict[str, Any]:
    return {
        "id": str(getattr(p, "id", "")),
        "tenant": getattr(p, "tenant", None),
        "provider": getattr(p, "provider", None),
        "purpose": getattr(p, "purpose", None),
        "data_categories": getattr(p, "data_categories", []) or [],
        "region": getattr(p, "region", None),
        "contract_ref": getattr(p, "contract_ref", None),
        "status": getattr(p, "status", None),
        "access_grants": getattr(p, "access_grants", []) or [],
        "created_at": getattr(p, "created_at", None).isoformat() if getattr(p, "created_at", None) else None,
    }


def _consent_to_dict(c) -> dict[str, Any]:
    return {
        "id": str(getattr(c, "id", "")),
        "tenant": getattr(c, "tenant", None),
        "subject": getattr(c, "subject", None),
        "purpose": getattr(c, "purpose", None),
        "scope": getattr(c, "scope", {}) or {},
        "version": getattr(c, "version", None),
        "status": getattr(c, "status", None),
        "created_at": getattr(c, "created_at", None).isoformat() if getattr(c, "created_at", None) else None,
    }


def _control_to_dict(c) -> dict[str, Any]:
    return {
        "id": str(getattr(c, "id", "")),
        "tenant": getattr(c, "tenant", None),
        "framework": getattr(c, "framework", None),
        "control_id": getattr(c, "control_id", None),
        "policy_id": getattr(c, "policy_id", None),
        "implementation": getattr(c, "implementation", None),
        "owner": getattr(c, "owner", None),
        "status": getattr(c, "status", None),
        "created_at": getattr(c, "created_at", None).isoformat() if getattr(c, "created_at", None) else None,
        "updated_at": getattr(c, "updated_at", None).isoformat() if getattr(c, "updated_at", None) else None,
    }


def _evidence_to_dict(e) -> dict[str, Any]:
    return {
        "id": str(getattr(e, "id", "")),
        "control_id": str(getattr(e, "control_id", "")),
        "tenant": getattr(e, "tenant", None),
        "evidence_type": getattr(e, "evidence_type", None),
        "source": getattr(e, "source", None),
        "hash": getattr(e, "hash", None),
        "valid_until": getattr(e, "valid_until", None).isoformat() if getattr(e, "valid_until", None) else None,
        "source_version": getattr(e, "source_version", None),
        "metadata_json": getattr(e, "metadata_json", {}) or {},
        "created_at": getattr(e, "created_at", None).isoformat() if getattr(e, "created_at", None) else None,
    }


# ── Pydantic request bodies ─────────────────────────────────────────────

class AssetCreateRequest(BaseModel):
    asset_id: str = Field(..., min_length=1, max_length=128)
    workspace: Optional[str] = Field(default=None, max_length=64)
    project: Optional[str] = Field(default=None, max_length=64)
    resource: str = Field(..., min_length=1, max_length=256)
    type: str = Field(..., min_length=1, max_length=64)
    owner: Optional[str] = Field(default=None, max_length=64)
    classification: str = Field(default="INTERNAL", max_length=32)
    source: Optional[str] = Field(default=None, max_length=256)
    location: Optional[str] = Field(default=None, max_length=512)
    retention_policy: Optional[str] = Field(default=None, max_length=64)
    sensitivity: Optional[str] = Field(default=None, max_length=32)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ClassifyRequest(BaseModel):
    level: str = Field(..., description="PUBLIC|INTERNAL|CONFIDENTIAL|RESTRICTED|SECRET")
    source: str = Field(..., description="schema|user|scanner|policy|provider|ai")
    confidence: float = Field(default=0.95, ge=0.0, le=1.0)
    evidence: dict[str, Any] = Field(default_factory=dict)
    advisory: bool = False


class AutoClassifyRequest(BaseModel):
    asset_id: str = Field(..., min_length=1, max_length=128)
    content_sample: str = Field(..., min_length=1, max_length=200000)


class DetectRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=200000)
    asset_id: Optional[str] = Field(default=None, max_length=128)


class LineageCreateRequest(BaseModel):
    source_asset: str = Field(..., min_length=1, max_length=128)
    target_asset: str = Field(..., min_length=1, max_length=128)
    transformation: str = Field(..., min_length=1, max_length=128)
    evidence: str = Field(..., min_length=1)
    stage: str = Field(..., description="discover|store|retrieve|model|output|export|transform")
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetentionPolicyCreateRequest(BaseModel):
    resource: Optional[str] = Field(default=None, max_length=128)
    classification: Optional[str] = Field(default=None, max_length=32)
    data_type: Optional[str] = Field(default=None, max_length=64)
    environment: Optional[str] = Field(default=None, max_length=64)
    retention_days: int = Field(..., gt=0)
    action: str = Field(default="delete", description="delete|anonymize|archive|export|transfer")


class RetentionHoldCreateRequest(BaseModel):
    scope: str = Field(..., min_length=1, max_length=256)
    reason: str = Field(..., min_length=1)


class DSRCreateRequest(BaseModel):
    request_type: str = Field(..., description="access|deletion|correction|restriction|export")
    subject: str = Field(..., min_length=1, max_length=256)
    scope: dict[str, Any] | list[str] | str | None = Field(default=None)


class DSRVerifyRequest(BaseModel):
    method: str = Field(..., min_length=1, description="mfa|government_id|document|knowledge|email etc")
    verifier: Optional[str] = Field(default=None, max_length=64)


class DSRApproveRequest(BaseModel):
    decision: str = Field(..., description="approved|rejected")
    approver: Optional[str] = Field(default=None, max_length=64)


class DSRCompleteRequest(BaseModel):
    systems: list[str] = Field(default_factory=list)
    completion: dict[str, Any] = Field(default_factory=dict)
    exceptions: list[dict[str, Any]] = Field(default_factory=list)


class ExportCreateRequest(BaseModel):
    request_id: Optional[str] = Field(default=None, max_length=64)
    scope: dict[str, Any] = Field(default_factory=dict)
    data_sources: list[str] = Field(default_factory=list)
    format: str = Field(default="json", max_length=32)
    ttl_hours: int = Field(default=24, gt=0, le=720)


class ExportVerifyRequest(BaseModel):
    token: str = Field(..., min_length=1)


class ProcessorCreateRequest(BaseModel):
    provider: str = Field(..., min_length=1, max_length=128)
    purpose: str = Field(..., min_length=1, max_length=256)
    data_categories: list[str] = Field(default_factory=list)
    region: Optional[str] = Field(default=None, max_length=32)
    contract_ref: Optional[str] = Field(default=None, max_length=256)
    status: str = Field(default="active", max_length=32)


class CrossBorderCheckRequest(BaseModel):
    source_region: Optional[str] = Field(default=None, max_length=64)
    processing_region: Optional[str] = Field(default=None, max_length=64)
    processor_id: Optional[str] = Field(default=None, max_length=64)
    asset_id: Optional[str] = Field(default=None, max_length=128)


class ConsentCreateRequest(BaseModel):
    subject: str = Field(..., min_length=1, max_length=256)
    purpose: str = Field(..., min_length=1, max_length=128)
    scope: dict[str, Any] = Field(default_factory=dict)
    version: str = Field(default="1.0", max_length=32)
    status: str = Field(default="granted", max_length=32)


class PolicyEvaluateRequest(BaseModel):
    actor: str = Field(..., min_length=1, max_length=64)
    resource: str = Field(..., min_length=1, max_length=256)
    policy_type: str = Field(..., min_length=1, max_length=64)
    context: dict[str, Any] = Field(default_factory=dict)


class PolicySimulateRequest(BaseModel):
    resource: str = Field(..., min_length=1, max_length=256)
    context: dict[str, Any] = Field(default_factory=dict)


class ControlCreateRequest(BaseModel):
    framework: str = Field(..., min_length=1, max_length=64)
    control_id: str = Field(..., min_length=1, max_length=64)
    policy_id: Optional[str] = Field(default=None, max_length=64)
    implementation: Optional[str] = Field(default=None)
    owner: Optional[str] = Field(default=None, max_length=64)


class EvidenceCreateRequest(BaseModel):
    evidence_type: str = Field(..., description="audit|config|test|scan|policy_eval|deployment|access_review|manual|log|attestation")
    source: str = Field(..., min_length=1, max_length=256)
    hash: Optional[str] = Field(default=None, max_length=128)
    valid_until: Optional[datetime] = None
    source_version: Optional[str] = Field(default=None, max_length=32)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ControlAssessRequest(BaseModel):
    status: str = Field(..., description="PASS|FAIL|PARTIAL|NOT_ASSESSED|NOT_APPLICABLE|IN_PROGRESS|DEFERRED")
    reason: Optional[str] = None


class LegalHoldCreateRequest2(BaseModel):
    scope: str = Field(..., min_length=1, max_length=256)
    reason: str = Field(..., min_length=1)


class ExceptionCreateRequest(BaseModel):
    policy_id: Optional[str] = Field(default=None, max_length=64)
    resource: Optional[str] = Field(default=None, max_length=256)
    reason: str = Field(..., min_length=1)
    scope: dict[str, Any] = Field(default_factory=dict)
    approval: Optional[str] = Field(default=None, max_length=64)
    expires_at: Optional[datetime] = None


class DLPScanRequest(BaseModel):
    destination: str = Field(..., min_length=1, max_length=128)
    content_sample: str = Field(..., min_length=1, max_length=200000)
    classification: Optional[str] = Field(default="INTERNAL", max_length=32)


class DLPRedactRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=200000)
    classification: Optional[str] = Field(default="INTERNAL", max_length=32)


# ── Assets ─────────────────────────────────────────────────────────────────

@router.post("/assets", status_code=status.HTTP_201_CREATED)
async def create_asset(body: AssetCreateRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _check_auth(current_user, tenant, "governance.asset.create", "governance_asset", body.asset_id)
    try:
        from app.datagov.catalog import catalog_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"catalog service unavailable: {exc}")
    try:
        row = await catalog_service.register_asset(db, tenant=tenant, asset_id=body.asset_id, workspace=body.workspace, project=body.project, resource=body.resource, type=body.type, owner=body.owner or str(current_user.id), classification=body.classification, source=body.source, location=body.location, retention_policy=body.retention_policy, sensitivity=body.sensitivity, metadata=body.metadata)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await _emit_event("governance.asset.discovered", {"asset_id": body.asset_id, "tenant": tenant, "resource": body.resource, "type": body.type}, tenant, str(current_user.id))
    _audit(str(current_user.id), tenant, "governance.asset.created", "governance_asset", body.asset_id, {"resource": body.resource, "type": body.type})
    return _asset_to_dict(row)


@router.get("/assets")
async def list_assets(current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db), type: Optional[str] = Query(None), classification: Optional[str] = Query(None), owner: Optional[str] = Query(None), workspace: Optional[str] = Query(None)):
    tenant = await _get_tenant(current_user, db)
    try:
        from app.datagov.catalog import catalog_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"catalog service unavailable: {exc}")
    filters: dict[str, Any] = {}
    if type:
        filters["type"] = type
    if classification:
        filters["classification"] = classification
    if owner:
        filters["owner"] = owner
    if workspace:
        filters["workspace"] = workspace
    rows = await catalog_service.list_assets(db, tenant=tenant, filters=filters)
    return [_asset_to_dict(r) for r in rows]


@router.get("/assets/{asset_id}")
async def get_asset(asset_id: str, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    try:
        from app.datagov.catalog import catalog_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"catalog service unavailable: {exc}")
    row = await catalog_service.get_asset(db, tenant=tenant, asset_id=asset_id)
    if not row:
        raise HTTPException(status_code=404, detail="Asset not found")
    return _asset_to_dict(row)


@router.post("/assets/discover")
async def discover_assets(current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _check_auth(current_user, tenant, "governance.asset.discover")
    try:
        from app.datagov.catalog import catalog_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"catalog service unavailable: {exc}")
    discovered = await catalog_service.discover_assets(db, tenant=tenant)
    await db.commit()
    await _emit_event("governance.asset.discovered", {"tenant": tenant, "discovered": discovered, "count": len(discovered)}, tenant, str(current_user.id))
    _audit(str(current_user.id), tenant, "governance.assets.discovered", "governance_asset", "", {"count": len(discovered)})
    return {"discovered": discovered, "count": len(discovered), "tenant": tenant}


# ── Classifications ────────────────────────────────────────────────────────

@router.post("/assets/{asset_id}/classify", status_code=status.HTTP_201_CREATED)
async def classify_asset(asset_id: str, body: ClassifyRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _check_auth(current_user, tenant, "governance.classification.create")
    try:
        from app.datagov.classifications import classification_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"classification service unavailable: {exc}")
    try:
        row = await classification_service.classify(db, tenant=tenant, asset_id=asset_id, level=body.level, source=body.source, confidence=body.confidence, evidence=body.evidence, classified_by=str(current_user.id), advisory=body.advisory)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await _emit_event("governance.data.classified", {"asset_id": asset_id, "level": body.level, "source": body.source, "tenant": tenant}, tenant, str(current_user.id))
    _audit(str(current_user.id), tenant, "governance.data.classified", "governance_classification", asset_id, {"level": body.level, "source": body.source})
    return _class_to_dict(row)


@router.get("/assets/{asset_id}/classifications")
async def list_classifications(asset_id: str, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    try:
        from app.datagov.models import GovernanceClassification  # type: ignore
        stmt = select(GovernanceClassification).where(GovernanceClassification.tenant == tenant, GovernanceClassification.asset_id == asset_id).order_by(GovernanceClassification.created_at.desc())
        result = await db.execute(stmt)
        rows = list(result.scalars().all())
        return [_class_to_dict(r) for r in rows]
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"classification model unavailable: {exc}")


@router.post("/classify/auto", status_code=status.HTTP_201_CREATED)
async def auto_classify(body: AutoClassifyRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    try:
        from app.datagov.classifications import classification_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"classification service unavailable: {exc}")
    try:
        row = await classification_service.auto_classify(db, tenant=tenant, asset_id=body.asset_id, content_sample=body.content_sample)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await _emit_event("governance.data.classified", {"asset_id": body.asset_id, "level": getattr(row, "level", None), "auto": True, "tenant": tenant}, tenant, str(current_user.id))
    _audit(str(current_user.id), tenant, "governance.data.auto_classified", "governance_classification", body.asset_id, {"level": getattr(row, "level", None)})
    return _class_to_dict(row)


@router.post("/classify/detect")
async def detect_sensitive(body: DetectRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    # tenant not strictly required for detection but validated for isolation consistency
    await _get_tenant(current_user, db)
    try:
        from app.datagov.classifications import classification_service  # type: ignore
        result = classification_service.detect_sensitive(body.content)
        return result
    except Exception:
        # fallback direct pattern scan without service
        try:
            from app.datagov.classifications import ClassificationService  # type: ignore
            svc = ClassificationService()
            return svc.detect_sensitive(body.content)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"detect service unavailable: {exc}")


# ── Lineage ────────────────────────────────────────────────────────────────

@router.post("/lineage", status_code=status.HTTP_201_CREATED)
async def record_lineage(body: LineageCreateRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _check_auth(current_user, tenant, "governance.lineage.create")
    try:
        from app.datagov.lineage import lineage_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"lineage service unavailable: {exc}")
    try:
        row = await lineage_service.record_edge(db, tenant=tenant, source_asset=body.source_asset, target_asset=body.target_asset, transformation=body.transformation, evidence=body.evidence, stage=body.stage, metadata=body.metadata)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await _emit_event("governance.lineage.updated", {"source_asset": body.source_asset, "target_asset": body.target_asset, "stage": body.stage, "tenant": tenant}, tenant, str(current_user.id))
    _audit(str(current_user.id), tenant, "governance.lineage.recorded", "governance_lineage", str(getattr(row, "id", "")), {"source": body.source_asset, "target": body.target_asset})
    return _lineage_to_dict(row)


@router.get("/lineage/{asset_id}/upstream")
async def lineage_upstream(asset_id: str, depth: int = Query(10, ge=1, le=50), current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    try:
        from app.datagov.lineage import lineage_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"lineage service unavailable: {exc}")
    try:
        edges = await lineage_service.trace_upstream(db, tenant=tenant, asset_id=asset_id, depth=depth)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"asset_id": asset_id, "direction": "upstream", "depth": depth, "count": len(edges), "edges": [_lineage_to_dict(e) for e in edges]}


@router.get("/lineage/{asset_id}/downstream")
async def lineage_downstream(asset_id: str, depth: int = Query(10, ge=1, le=50), current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    try:
        from app.datagov.lineage import lineage_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"lineage service unavailable: {exc}")
    try:
        edges = await lineage_service.trace_downstream(db, tenant=tenant, asset_id=asset_id, depth=depth)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"asset_id": asset_id, "direction": "downstream", "depth": depth, "count": len(edges), "edges": [_lineage_to_dict(e) for e in edges]}


@router.get("/lineage/{asset_id}/impact")
async def lineage_impact(asset_id: str, depth: int = Query(10, ge=1, le=50), current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    try:
        from app.datagov.lineage import lineage_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"lineage service unavailable: {exc}")
    try:
        result = await lineage_service.impact_analysis(db, tenant=tenant, asset_id=asset_id, depth=depth)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    edges = result.get("edges", [])
    return {"asset_id": asset_id, "depth": depth, "impact_count": result.get("impact_count", 0), "impacted_assets": result.get("impacted_assets", []), "edge_count": result.get("edge_count", len(edges)), "edges": [_lineage_to_dict(e) for e in edges]}


# ── Retention ──────────────────────────────────────────────────────────────

@router.post("/retention/policies", status_code=status.HTTP_201_CREATED)
async def create_retention_policy(body: RetentionPolicyCreateRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _check_auth(current_user, tenant, "governance.retention.create")
    try:
        from app.datagov.retention import retention_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"retention service unavailable: {exc}")
    try:
        row = await retention_service.create_policy(db, tenant=tenant, resource=body.resource, classification=body.classification, data_type=body.data_type, environment=body.environment, retention_days=body.retention_days, action=body.action)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await _emit_event("governance.retention.violation", {"policy_id": str(getattr(row, "id", "")), "action": body.action, "tenant": tenant}, tenant, str(current_user.id))
    _audit(str(current_user.id), tenant, "governance.retention.policy.created", "governance_retention", str(getattr(row, "id", "")), {"action": body.action})
    return _retention_to_dict(row)


@router.get("/retention/policies")
async def list_retention_policies(current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    try:
        from app.datagov.retention import retention_service  # type: ignore
        rows = await retention_service.list_policies(db, tenant=tenant)
        return [_retention_to_dict(r) for r in rows]
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"retention service unavailable: {exc}")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/retention/check")
async def retention_check(asset_id: Optional[str] = Query(None), current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    try:
        from app.datagov.retention import retention_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"retention service unavailable: {exc}")
    if asset_id:
        # single asset state
        try:
            from app.datagov.models import GovernanceDataAsset  # type: ignore
            stmt = select(GovernanceDataAsset).where(GovernanceDataAsset.tenant == tenant, GovernanceDataAsset.asset_id == asset_id)
            result = await db.execute(stmt)
            asset = result.scalars().first()
            if not asset:
                raise HTTPException(status_code=404, detail="Asset not found")
            state = await retention_service.evaluate_asset(db, tenant=tenant, asset=asset)
            return {"asset_id": asset_id, "state": state, "tenant": tenant}
        except HTTPException:
            raise
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
    else:
        try:
            expired = await retention_service.check_expired(db, tenant=tenant)
            out = []
            for entry in expired:
                out.append({"asset_id": entry.get("asset_id"), "state": entry.get("state"), "retention_days": entry.get("retention_days"), "age_days": entry.get("age_days"), "policy_id": entry.get("policy_id"), "action": entry.get("action")})
            return {"tenant": tenant, "count": len(out), "items": out}
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))


@router.post("/retention/holds", status_code=status.HTTP_201_CREATED)
async def create_retention_hold(body: RetentionHoldCreateRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _check_auth(current_user, tenant, "governance.legal_hold.create")
    try:
        from app.datagov.retention import retention_service  # type: ignore
        row = await retention_service.create_hold(db, tenant=tenant, scope=body.scope, reason=body.reason, created_by=str(current_user.id))
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"retention service unavailable: {exc}")
    await _emit_event("governance.legal_hold.created", {"hold_id": str(getattr(row, "id", "")), "scope": body.scope, "tenant": tenant}, tenant, str(current_user.id))
    _audit(str(current_user.id), tenant, "governance.legal_hold.created", "governance_legal_hold", str(getattr(row, "id", "")), {"scope": body.scope})
    return {"id": str(getattr(row, "id", "")), "tenant": getattr(row, "tenant", tenant), "scope": getattr(row, "scope", body.scope), "reason": getattr(row, "reason", body.reason), "created_by": getattr(row, "created_by", str(current_user.id)), "created_at": getattr(row, "created_at", None).isoformat() if getattr(row, "created_at", None) else None}


@router.get("/retention/holds")
async def list_retention_holds(current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    try:
        from app.datagov.models import GovernanceLegalHold  # type: ignore
        stmt = select(GovernanceLegalHold).where(GovernanceLegalHold.tenant == tenant).order_by(GovernanceLegalHold.created_at.desc())
        result = await db.execute(stmt)
        rows = list(result.scalars().all())
        return [{"id": str(r.id), "tenant": r.tenant, "scope": r.scope, "reason": r.reason, "created_by": r.created_by, "released_at": r.released_at.isoformat() if r.released_at else None, "released_by": r.released_by, "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"holds unavailable: {exc}")


@router.delete("/retention/holds/{hold_id}")
async def delete_retention_hold(hold_id: str, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _check_auth(current_user, tenant, "governance.legal_hold.delete")
    try:
        from app.datagov.retention import retention_service  # type: ignore
        row = await retention_service.release_hold(db, tenant=tenant, hold_id=hold_id, released_by=str(current_user.id))
        await db.commit()
        return {"id": str(getattr(row, "id", hold_id)), "released_at": getattr(row, "released_at", None).isoformat() if getattr(row, "released_at", None) else None, "released_by": getattr(row, "released_by", None)}
    except ValueError as e:
        msg = str(e).lower()
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=422, detail=str(e))
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"retention service unavailable: {exc}")


# ── DSR (requests) ─────────────────────────────────────────────────────────

@router.post("/requests", status_code=status.HTTP_201_CREATED)
async def create_dsr(body: DSRCreateRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _check_auth(current_user, tenant, "governance.dsr.create")
    try:
        from app.datagov.dsr import dsr_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"dsr service unavailable: {exc}")
    try:
        row = await dsr_service.create_request(db, tenant=tenant, request_type=body.request_type, subject=body.subject, scope=body.scope, requested_by=str(current_user.id))
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await _emit_event("governance.request.created", {"request_id": str(getattr(row, "id", "")), "request_type": body.request_type, "subject": body.subject, "tenant": tenant}, tenant, str(current_user.id))
    _audit(str(current_user.id), tenant, "governance.dsr.created", "governance_data_request", str(getattr(row, "id", "")), {"request_type": body.request_type})
    return _request_to_dict(row)


@router.get("/requests")
async def list_dsrs(request_type: Optional[str] = Query(None), subject: Optional[str] = Query(None), current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    try:
        from app.datagov.dsr import dsr_service  # type: ignore
        rows = await dsr_service.list_requests(db, tenant=tenant, request_type=request_type, subject=subject)
        return [_request_to_dict(r) for r in rows]
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"dsr service unavailable: {exc}")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/requests/{request_id}")
async def get_dsr(request_id: str, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    try:
        from app.datagov.dsr import dsr_service  # type: ignore
        row = await dsr_service.get_request(db, tenant=tenant, request_id=request_id)
        if not row:
            raise HTTPException(status_code=404, detail="Request not found")
        return _request_to_dict(row)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"dsr service unavailable: {exc}")


@router.post("/requests/{request_id}/verify")
async def verify_dsr(request_id: str, body: DSRVerifyRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    try:
        from app.datagov.dsr import dsr_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"dsr service unavailable: {exc}")
    verifier = body.verifier or str(current_user.id)
    # tenant check: ensure request belongs to tenant if service enforces
    try:
        check = await dsr_service.get_request(db, tenant=tenant, request_id=request_id)
        if not check:
            raise HTTPException(status_code=404, detail="Request not found")
    except HTTPException:
        raise
    except Exception:
        pass
    try:
        row = await dsr_service.verify_identity(db, request_id=request_id, verifier=verifier, method=body.method)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    _audit(str(current_user.id), tenant, "governance.dsr.verified", "governance_data_request", request_id, {"method": body.method})
    return _request_to_dict(row)


@router.post("/requests/{request_id}/approve")
async def approve_dsr(request_id: str, body: DSRApproveRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _check_auth(current_user, tenant, "governance.dsr.approve")
    try:
        from app.datagov.dsr import dsr_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"dsr service unavailable: {exc}")
    try:
        check = await dsr_service.get_request(db, tenant=tenant, request_id=request_id)
        if not check:
            raise HTTPException(status_code=404, detail="Request not found")
    except HTTPException:
        raise
    except Exception:
        pass
    approver = body.approver or str(current_user.id)
    try:
        row = await dsr_service.approve_request(db, request_id=request_id, approver=approver, decision=body.decision)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    _audit(str(current_user.id), tenant, "governance.dsr.approved", "governance_data_request", request_id, {"decision": body.decision})
    return _request_to_dict(row)


@router.post("/requests/{request_id}/complete")
async def complete_dsr(request_id: str, body: DSRCompleteRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _check_auth(current_user, tenant, "governance.dsr.complete")
    try:
        from app.datagov.dsr import dsr_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"dsr service unavailable: {exc}")
    try:
        check = await dsr_service.get_request(db, tenant=tenant, request_id=request_id)
        if not check:
            raise HTTPException(status_code=404, detail="Request not found")
    except HTTPException:
        raise
    except Exception:
        pass
    try:
        row = await dsr_service.complete_request(db, request_id=request_id, systems=body.systems, completion=body.completion, exceptions=body.exceptions)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await _emit_event("governance.request.created", {"request_id": request_id, "action": "completed", "tenant": tenant}, tenant, str(current_user.id))
    _audit(str(current_user.id), tenant, "governance.dsr.completed", "governance_data_request", request_id, {"systems": body.systems})
    return _request_to_dict(row)


# ── Exports ────────────────────────────────────────────────────────────────

@router.post("/exports", status_code=status.HTTP_201_CREATED)
async def create_export(body: ExportCreateRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _check_auth(current_user, tenant, "governance.export.create")
    try:
        from app.datagov.exports import export_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"export service unavailable: {exc}")
    try:
        row = await export_service.create_export(db, tenant=tenant, request_id=body.request_id, requester=str(current_user.id), scope=body.scope, data_sources=body.data_sources, format=body.format, ttl_hours=body.ttl_hours)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await _emit_event("governance.export.completed", {"export_id": str(getattr(row, "id", "")), "tenant": tenant, "format": body.format}, tenant, str(current_user.id))
    _audit(str(current_user.id), tenant, "governance.export.created", "governance_export", str(getattr(row, "id", "")), {"format": body.format})
    out = _export_to_dict(row)
    # expose one-time token if service set ephemeral attr
    token = getattr(row, "_raw_token", None) or getattr(row, "_token", None) or getattr(row, "token", None)
    if token:
        out["token"] = token
    return out


@router.get("/exports")
async def list_exports(current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    try:
        from app.datagov.exports import export_service  # type: ignore
        rows = await export_service.list_exports(db, tenant=tenant)
        return [_export_to_dict(r) for r in rows]
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"export service unavailable: {exc}")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/exports/{export_id}")
async def get_export(export_id: str, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    try:
        from app.datagov.exports import export_service  # type: ignore
        row = await export_service.get_export(db, export_id=export_id, tenant=tenant)
        if not row:
            raise HTTPException(status_code=404, detail="Export not found")
        return _export_to_dict(row)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"export service unavailable: {exc}")


@router.post("/exports/{export_id}/verify")
async def verify_export(export_id: str, body: ExportVerifyRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    await _get_tenant(current_user, db)
    try:
        from app.datagov.exports import export_service  # type: ignore
        # verify by token, but also ensure export_id matches if returned
        row = await export_service.verify_token(db, token=body.token)
        if not row:
            raise HTTPException(status_code=404, detail="Invalid or expired token")
        if str(getattr(row, "id", "")) != export_id:
            # token belongs to different export
            raise HTTPException(status_code=422, detail="Token does not match export_id")
        return {"verified": True, "export": _export_to_dict(row)}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"export service unavailable: {exc}")


@router.post("/exports/{export_id}/revoke")
async def revoke_export(export_id: str, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _check_auth(current_user, tenant, "governance.export.revoke")
    try:
        from app.datagov.exports import export_service  # type: ignore
        row = await export_service.revoke(db, export_id=export_id, tenant=tenant)
        await db.commit()
        _audit(str(current_user.id), tenant, "governance.export.revoked", "governance_export", export_id, {})
        return _export_to_dict(row)
    except ValueError as e:
        msg = str(e).lower()
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=422, detail=str(e))
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"export service unavailable: {exc}")


# ── Processors ─────────────────────────────────────────────────────────────

@router.post("/processors", status_code=status.HTTP_201_CREATED)
async def create_processor(body: ProcessorCreateRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _check_auth(current_user, tenant, "governance.processor.create")
    try:
        from app.datagov.processors import processor_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"processor service unavailable: {exc}")
    try:
        row = await processor_service.register_processor(db, tenant=tenant, provider=body.provider, purpose=body.purpose, data_categories=body.data_categories, region=body.region, contract_ref=body.contract_ref, status=body.status)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    _audit(str(current_user.id), tenant, "governance.processor.created", "governance_processor", str(getattr(row, "id", "")), {"provider": body.provider})
    return _processor_to_dict(row)


@router.get("/processors")
async def list_processors(current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    try:
        from app.datagov.processors import processor_service  # type: ignore
        rows = await processor_service.list_processors(db, tenant=tenant)
        return [_processor_to_dict(r) for r in rows]
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"processor service unavailable: {exc}")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/processors/{processor_id}")
async def get_processor(processor_id: str, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    try:
        from app.datagov.processors import processor_service  # type: ignore
        row = await processor_service.get_processor(db, tenant=tenant, processor_id=processor_id)
        if not row:
            raise HTTPException(status_code=404, detail="Processor not found")
        return _processor_to_dict(row)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"processor service unavailable: {exc}")


@router.post("/processors/{processor_id}/revoke")
async def revoke_processor(processor_id: str, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _check_auth(current_user, tenant, "governance.processor.revoke")
    try:
        from app.datagov.processors import processor_service  # type: ignore
        row = await processor_service.revoke_access(db, tenant=tenant, processor_id=processor_id, actor=str(current_user.id), reason="revoked via api")
        await db.commit()
        _audit(str(current_user.id), tenant, "governance.processor.revoked", "governance_processor", processor_id, {})
        return _processor_to_dict(row)
    except ValueError as e:
        msg = str(e).lower()
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=422, detail=str(e))
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"processor service unavailable: {exc}")


@router.post("/processors/check-cross-border")
async def check_cross_border(body: CrossBorderCheckRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    try:
        from app.datagov.processors import processor_service  # type: ignore
        result = await processor_service.check_cross_border(db, tenant=tenant, source_region=body.source_region, processing_region=body.processing_region, processor_id=body.processor_id, asset_id=body.asset_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"processor service unavailable: {exc}")


# ── Consents ───────────────────────────────────────────────────────────────

@router.post("/consents", status_code=status.HTTP_201_CREATED)
async def create_consent(body: ConsentCreateRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _check_auth(current_user, tenant, "governance.consent.create")
    try:
        from app.datagov.consents import consent_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"consent service unavailable: {exc}")
    try:
        row = await consent_service.record_consent(db, tenant=tenant, subject=body.subject, purpose=body.purpose, scope=body.scope, version=body.version, status=body.status)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    _audit(str(current_user.id), tenant, "governance.consent.created", "governance_consent", str(getattr(row, "id", "")), {"purpose": body.purpose})
    return _consent_to_dict(row)


@router.get("/consents")
async def list_consents(subject: Optional[str] = Query(None), current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    try:
        from app.datagov.consents import consent_service  # type: ignore
        rows = await consent_service.list_consents(db, tenant=tenant, subject=subject)
        return [_consent_to_dict(r) for r in rows]
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"consent service unavailable: {exc}")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/consents/{consent_id}/withdraw")
async def withdraw_consent(consent_id: str, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _check_auth(current_user, tenant, "governance.consent.withdraw")
    try:
        from app.datagov.consents import consent_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"consent service unavailable: {exc}")
    # verify tenant ownership if possible
    try:
        check = await consent_service.get_consent(db, tenant=tenant, consent_id=consent_id)
        if not check:
            raise HTTPException(status_code=404, detail="Consent not found")
    except HTTPException:
        raise
    except Exception:
        pass
    try:
        result = await consent_service.withdraw_consent(db, consent_id=consent_id, actor=str(current_user.id))
        await db.commit()
        consent = result.get("consent")
        affected = result.get("affected_asset_ids", [])
        exceptions = result.get("exceptions", [])
        await _emit_event("governance.consent.withdrawn", {"consent_id": consent_id, "tenant": tenant, "affected_count": len(affected)}, tenant, str(current_user.id))
        _audit(str(current_user.id), tenant, "governance.consent.withdrawn", "governance_consent", consent_id, {"affected": len(affected)})
        return {"consent": _consent_to_dict(consent) if consent is not None else {"id": consent_id}, "affected_asset_ids": affected, "exceptions": exceptions}
    except ValueError as e:
        msg = str(e).lower()
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=422, detail=str(e))


# ── Policies ───────────────────────────────────────────────────────────────

@router.post("/policies/evaluate")
async def evaluate_policy(body: PolicyEvaluateRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    try:
        from app.datagov.policy_bridge import policy_bridge_service  # type: ignore
        result = await policy_bridge_service.evaluate(db, tenant=tenant, actor=body.actor, resource=body.resource, policy_type=body.policy_type, context=body.context)
        await db.commit()
        await _emit_event("governance.policy.violation" if result.get("decision") == "DENY" else "governance.policy.evaluated", {"resource": body.resource, "decision": result.get("decision"), "tenant": tenant}, tenant, body.actor)
        _audit(body.actor, tenant, "governance.policy.evaluated", "governance_policy_decision", str(result.get("persisted_id", "")), {"decision": result.get("decision")})
        return result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"policy_bridge unavailable: {exc}")


@router.post("/policies/simulate")
async def simulate_policy(body: PolicySimulateRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    try:
        from app.datagov.policy_bridge import policy_bridge_service  # type: ignore
        result = await policy_bridge_service.simulate(db, tenant=tenant, resource=body.resource, context=body.context)
        return result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"policy_bridge unavailable: {exc}")


@router.get("/policies/decisions")
async def list_policy_decisions(limit: int = Query(50, ge=1, le=200), current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    try:
        from app.datagov.models import GovernancePolicyDecision  # type: ignore
        stmt = select(GovernancePolicyDecision).where(GovernancePolicyDecision.tenant == tenant).order_by(GovernancePolicyDecision.created_at.desc()).limit(limit)
        result = await db.execute(stmt)
        rows = list(result.scalars().all())
        return [{"id": str(r.id), "tenant": r.tenant, "actor": r.actor, "resource": r.resource, "policy_id": r.policy_id, "policy_version": r.policy_version, "decision": r.decision, "reason": r.reason, "request_id": r.request_id, "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"decisions unavailable: {exc}")


# ── Controls ───────────────────────────────────────────────────────────────

@router.post("/controls", status_code=status.HTTP_201_CREATED)
async def create_control(body: ControlCreateRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _check_auth(current_user, tenant, "governance.control.create")
    try:
        from app.datagov.controls import control_service  # type: ignore
        row = await control_service.create_control(db, tenant=tenant, framework=body.framework, control_id=body.control_id, policy_id=body.policy_id, implementation=body.implementation, owner=body.owner or str(current_user.id))
        await db.commit()
    except ValueError as e:
        msg = str(e).lower()
        if "already exists" in msg:
            raise HTTPException(status_code=409, detail=str(e))
        raise HTTPException(status_code=422, detail=str(e))
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"control service unavailable: {exc}")
    await _emit_event("governance.control.status_changed", {"control_id": str(getattr(row, "id", "")), "framework": body.framework, "tenant": tenant}, tenant, str(current_user.id))
    _audit(str(current_user.id), tenant, "governance.control.created", "governance_control", str(getattr(row, "id", "")), {"control_id": body.control_id})
    return _control_to_dict(row)


@router.get("/controls")
async def list_controls(framework: Optional[str] = Query(None), status_filter: Optional[str] = Query(None, alias="status"), current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    try:
        from app.datagov.controls import control_service  # type: ignore
        rows = await control_service.list_controls(db, tenant=tenant, framework=framework, status=status_filter)
        return [_control_to_dict(r) for r in rows]
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"control service unavailable: {exc}")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/controls/{control_id}/evidence", status_code=status.HTTP_201_CREATED)
async def add_evidence(control_id: str, body: EvidenceCreateRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _check_auth(current_user, tenant, "governance.evidence.create")
    try:
        from app.datagov.controls import control_service  # type: ignore
        row = await control_service.collect_evidence(db, control_id=control_id, tenant=tenant, evidence_type=body.evidence_type, source=body.source, hash=body.hash, valid_until=body.valid_until, source_version=body.source_version, metadata=body.metadata)
        await db.commit()
    except ValueError as e:
        msg = str(e).lower()
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=422, detail=str(e))
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"control service unavailable: {exc}")
    await _emit_event("governance.evidence.collected", {"control_id": control_id, "evidence_type": body.evidence_type, "tenant": tenant}, tenant, str(current_user.id))
    _audit(str(current_user.id), tenant, "governance.evidence.collected", "governance_control_evidence", str(getattr(row, "id", "")), {"control_id": control_id})
    return _evidence_to_dict(row)


@router.get("/controls/{control_id}/evidence")
async def list_evidence(control_id: str, include_expired: bool = Query(True), current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    try:
        from app.datagov.controls import control_service  # type: ignore
        rows = await control_service.get_evidence(db, tenant=tenant, control_id=control_id, include_expired=include_expired)
        return [_evidence_to_dict(r) for r in rows]
    except ValueError as e:
        msg = str(e).lower()
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=422, detail=str(e))
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"control service unavailable: {exc}")


@router.post("/controls/{control_id}/assess")
async def assess_control(control_id: str, body: ControlAssessRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _check_auth(current_user, tenant, "governance.control.assess")
    try:
        from app.datagov.controls import control_service  # type: ignore
        row = await control_service.assess_control(db, control_id=control_id, status=body.status, actor=str(current_user.id), tenant=tenant, reason=body.reason)
        await db.commit()
    except ValueError as e:
        msg = str(e).lower()
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=str(e))
        if "without valid evidence" in msg:
            raise HTTPException(status_code=422, detail=str(e))
        raise HTTPException(status_code=422, detail=str(e))
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"control service unavailable: {exc}")
    await _emit_event("governance.control.status_changed", {"control_id": control_id, "status": body.status, "tenant": tenant}, tenant, str(current_user.id))
    _audit(str(current_user.id), tenant, "governance.control.assessed", "governance_control", control_id, {"status": body.status})
    return _control_to_dict(row)


@router.get("/controls/package")
async def get_controls_package(framework: Optional[str] = Query(None), current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    try:
        from app.datagov.controls import control_service  # type: ignore
        pkg = await control_service.build_package(db, tenant=tenant, framework=framework)
        return pkg
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"control service unavailable: {exc}")


# ── Legal holds (alias) ────────────────────────────────────────────────────

@router.post("/legal-holds", status_code=status.HTTP_201_CREATED)
async def create_legal_hold(body: LegalHoldCreateRequest2, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _check_auth(current_user, tenant, "governance.legal_hold.create")
    try:
        from app.datagov.retention import retention_service  # type: ignore
        row = await retention_service.create_hold(db, tenant=tenant, scope=body.scope, reason=body.reason, created_by=str(current_user.id))
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ImportError:
        # fallback to controls exception_service alias
        try:
            from app.datagov.controls import exception_service  # type: ignore
            row = await exception_service.create_hold(db, tenant=tenant, scope=body.scope, reason=body.reason, created_by=str(current_user.id))
            await db.commit()
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"legal hold service unavailable: {exc}")
    await _emit_event("governance.legal_hold.created", {"hold_id": str(getattr(row, "id", "")), "scope": body.scope, "tenant": tenant}, tenant, str(current_user.id))
    _audit(str(current_user.id), tenant, "governance.legal_hold.created", "governance_legal_hold", str(getattr(row, "id", "")), {"scope": body.scope})
    return {"id": str(getattr(row, "id", "")), "tenant": getattr(row, "tenant", tenant), "scope": getattr(row, "scope", body.scope), "reason": getattr(row, "reason", body.reason), "created_by": getattr(row, "created_by", str(current_user.id)), "created_at": getattr(row, "created_at", None).isoformat() if getattr(row, "created_at", None) else None}


@router.get("/legal-holds")
async def list_legal_holds(current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    try:
        from app.datagov.models import GovernanceLegalHold  # type: ignore
        stmt = select(GovernanceLegalHold).where(GovernanceLegalHold.tenant == tenant).order_by(GovernanceLegalHold.created_at.desc())
        result = await db.execute(stmt)
        rows = list(result.scalars().all())
        return [{"id": str(r.id), "tenant": r.tenant, "scope": r.scope, "reason": r.reason, "created_by": r.created_by, "released_at": r.released_at.isoformat() if r.released_at else None, "released_by": r.released_by, "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"holds unavailable: {exc}")


@router.delete("/legal-holds/{hold_id}")
async def delete_legal_hold(hold_id: str, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _check_auth(current_user, tenant, "governance.legal_hold.delete")
    try:
        from app.datagov.retention import retention_service  # type: ignore
        row = await retention_service.release_hold(db, tenant=tenant, hold_id=hold_id, released_by=str(current_user.id))
        await db.commit()
        return {"id": str(getattr(row, "id", hold_id)), "released_at": getattr(row, "released_at", None).isoformat() if getattr(row, "released_at", None) else None, "released_by": getattr(row, "released_by", None)}
    except ValueError as e:
        msg = str(e).lower()
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=422, detail=str(e))
    except ImportError:
        try:
            from app.datagov.controls import exception_service  # type: ignore
            row = await exception_service.release_hold(db, tenant=tenant, hold_id=hold_id, released_by=str(current_user.id))
            await db.commit()
            return {"id": str(getattr(row, "id", hold_id)), "released_at": getattr(row, "released_at", None).isoformat() if getattr(row, "released_at", None) else None}
        except ValueError as e:
            msg = str(e).lower()
            if "not found" in msg:
                raise HTTPException(status_code=404, detail=str(e))
            raise HTTPException(status_code=422, detail=str(e))
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"legal hold service unavailable: {exc}")


# ── Exceptions ─────────────────────────────────────────────────────────────

@router.post("/exceptions", status_code=status.HTTP_201_CREATED)
async def create_exception(body: ExceptionCreateRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _check_auth(current_user, tenant, "governance.exception.create")
    try:
        from app.datagov.controls import exception_service  # type: ignore
        row = await exception_service.create_exception(db, tenant=tenant, policy_id=body.policy_id, resource=body.resource, reason=body.reason, scope=body.scope, owner=str(current_user.id), approval=body.approval, expires_at=body.expires_at)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"exception service unavailable: {exc}")
    _audit(str(current_user.id), tenant, "governance.exception.created", "governance_exception", str(getattr(row, "id", "")), {"resource": body.resource})
    return {"id": str(getattr(row, "id", "")), "tenant": getattr(row, "tenant", tenant), "policy_id": getattr(row, "policy_id", body.policy_id), "resource": getattr(row, "resource", body.resource), "reason": getattr(row, "reason", body.reason), "scope": getattr(row, "scope", body.scope), "owner": getattr(row, "owner", str(current_user.id)), "approval": getattr(row, "approval", body.approval), "expires_at": getattr(row, "expires_at", None).isoformat() if getattr(row, "expires_at", None) else None, "created_at": getattr(row, "created_at", None).isoformat() if getattr(row, "created_at", None) else None}


@router.get("/exceptions")
async def list_exceptions(include_expired: bool = Query(False), current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    try:
        from app.datagov.controls import exception_service  # type: ignore
        rows = await exception_service.list_exceptions(db, tenant=tenant, include_expired=include_expired)
        return [{"id": str(r.id), "tenant": r.tenant, "policy_id": r.policy_id, "resource": r.resource, "reason": r.reason, "scope": r.scope, "owner": r.owner, "approval": r.approval, "expires_at": r.expires_at.isoformat() if r.expires_at else None, "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"exception service unavailable: {exc}")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.delete("/exceptions/{exception_id}")
async def delete_exception(exception_id: str, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    _check_auth(current_user, tenant, "governance.exception.delete")
    try:
        from app.datagov.models import GovernanceException  # type: ignore
        stmt = select(GovernanceException).where(GovernanceException.tenant == tenant, GovernanceException.id == _parse_uuid(exception_id, "exception_id"))
        result = await db.execute(stmt)
        row = result.scalars().first()
        if not row:
            raise HTTPException(status_code=404, detail="Exception not found")
        await db.delete(row)
        await db.commit()
        _audit(str(current_user.id), tenant, "governance.exception.deleted", "governance_exception", exception_id, {})
        return {"deleted": True, "id": exception_id}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as exc:
        # fallback try string id without uuid parse
        try:
            from app.datagov.models import GovernanceException as _M
            stmt2 = select(_M).where(_M.tenant == tenant)
            # manual filter by str id
            res2 = await db.execute(select(_M).where(_M.tenant == tenant))
            for r in list(res2.scalars().all()):
                if str(r.id) == exception_id:
                    await db.delete(r)
                    await db.commit()
                    return {"deleted": True, "id": exception_id}
            raise HTTPException(status_code=404, detail="Exception not found")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=503, detail=f"delete failed: {exc}")


# ── DLP ────────────────────────────────────────────────────────────────────

@router.post("/dlp/scan")
async def dlp_scan(body: DLPScanRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    try:
        from app.datagov.dlp import dlp_service  # type: ignore
        result = await dlp_service.scan(db, tenant=tenant, actor=str(current_user.id), destination=body.destination, content_sample=body.content_sample, classification=body.classification)
        await db.commit()
        if result.get("action") in ("BLOCK", "REQUIRE_APPROVAL"):
            await _emit_event("governance.dlp.violation", {"destination": body.destination, "classification": body.classification, "action": result.get("action"), "tenant": tenant}, tenant, str(current_user.id))
        elif result.get("action") == "REDACT":
            await _emit_event("data.redacted", {"destination": body.destination, "tenant": tenant}, tenant, str(current_user.id))
        _audit(str(current_user.id), tenant, f"governance.dlp.{result.get('action','scan').lower()}", "governance_dlp", body.destination, {"classification": body.classification})
        return result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"dlp service unavailable: {exc}")


@router.get("/dlp/events")
async def list_dlp_events(limit: int = Query(50, ge=1, le=200), current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    try:
        from app.datagov.models import GovernanceDLPEvent  # type: ignore
        stmt = select(GovernanceDLPEvent).where(GovernanceDLPEvent.tenant == tenant).order_by(GovernanceDLPEvent.created_at.desc()).limit(limit)
        result = await db.execute(stmt)
        rows = list(result.scalars().all())
        return [{"id": str(r.id), "tenant": r.tenant, "event_type": r.event_type, "actor": r.actor, "resource": r.resource, "action": r.action, "details": r.details, "idempotency_key": r.idempotency_key, "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"dlp events unavailable: {exc}")


@router.post("/dlp/redact")
async def dlp_redact(body: DLPRedactRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    await _get_tenant(current_user, db)
    try:
        from app.datagov.dlp import apply_redaction  # type: ignore
        redacted = apply_redaction(body.content, body.classification)
        await _emit_event("data.redacted", {"classification": body.classification, "length": len(body.content)}, None, str(current_user.id))
        return {"redacted": redacted, "classification": body.classification}
    except ImportError:
        try:
            from app.datagov.dlp import dlp_service  # type: ignore
            # fallback scan then extract redacted
            from app.datagov.dlp import apply_redaction as _ar  # type: ignore
            return {"redacted": _ar(body.content, body.classification), "classification": body.classification}
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"redact unavailable: {exc}")

# ── Risk ───────────────────────────────────────────────────────────────────

@router.get("/risk/{asset_id}")
async def get_risk(asset_id: str, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    try:
        from app.datagov.risk import risk_service  # type: ignore
        result = await risk_service.calculate_risk(db, tenant=tenant, asset_id=asset_id)
        return result
    except ValueError as e:
        msg = str(e).lower()
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=422, detail=str(e))
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"risk service unavailable: {exc}")


# ── Dashboard ──────────────────────────────────────────────────────────────

@router.get("/dashboard")
async def get_dashboard(current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await _get_tenant(current_user, db)
    out: dict[str, Any] = {"tenant": tenant, "generated_at": datetime.now(timezone.utc).isoformat()}
    # assets
    try:
        from app.datagov.catalog import catalog_service  # type: ignore
        assets = await catalog_service.list_assets(db, tenant=tenant)
        out["assets_total"] = len(assets)
        by_class: dict[str, int] = {}
        for a in assets:
            k = (getattr(a, "classification", "UNKNOWN") or "UNKNOWN")
            by_class[k] = by_class.get(k, 0) + 1
        out["assets_by_classification"] = by_class
    except Exception as exc:
        logger.debug("dashboard assets failed: %s", exc)
        out["assets_total"] = 0
        out["assets_by_classification"] = {}
    # classifications total
    try:
        from app.datagov.models import GovernanceClassification  # type: ignore
        stmt = select(GovernanceClassification).where(GovernanceClassification.tenant == tenant)
        result = await db.execute(stmt)
        rows = list(result.scalars().all())
        out["classifications_total"] = len(rows)
        adv = sum(1 for r in rows if getattr(r, "advisory", False))
        out["advisory_classifications"] = adv
    except Exception as exc:
        logger.debug("dashboard classifications failed: %s", exc)
        out["classifications_total"] = 0
    # retention check
    try:
        from app.datagov.retention import retention_service  # type: ignore
        expired = await retention_service.check_expired(db, tenant=tenant)
        out["retention_expiring"] = len(expired)
        out["retention_expired_items"] = [{"asset_id": e.get("asset_id"), "state": e.get("state")} for e in expired[:10]]
    except Exception as exc:
        logger.debug("dashboard retention failed: %s", exc)
        out["retention_expiring"] = 0
    # DSR pending
    try:
        from app.datagov.dsr import dsr_service  # type: ignore
        reqs = await dsr_service.list_requests(db, tenant=tenant)
        out["dsr_total"] = len(reqs)
        out["dsr_pending_verification"] = sum(1 for r in reqs if getattr(r, "verification_status", "") == "pending")
        out["dsr_pending_approval"] = sum(1 for r in reqs if getattr(r, "approval_status", "") == "pending")
    except Exception:
        out["dsr_total"] = 0
    # exports
    try:
        from app.datagov.exports import export_service  # type: ignore
        exps = await export_service.list_exports(db, tenant=tenant)
        out["exports_total"] = len(exps)
        out["exports_active"] = sum(1 for e in exps if getattr(e, "status", "") not in ("expired", "revoked"))
    except Exception:
        out["exports_total"] = 0
    # processors
    try:
        from app.datagov.processors import processor_service  # type: ignore
        procs = await processor_service.list_processors(db, tenant=tenant)
        out["processors_total"] = len(procs)
        out["processors_revoked"] = sum(1 for p in procs if getattr(p, "status", "") == "revoked")
    except Exception:
        out["processors_total"] = 0
    # consents
    try:
        from app.datagov.consents import consent_service  # type: ignore
        cons = await consent_service.list_consents(db, tenant=tenant)
        out["consents_total"] = len(cons)
        out["consents_withdrawn"] = sum(1 for c in cons if getattr(c, "status", "") == "withdrawn")
    except Exception:
        out["consents_total"] = 0
    # controls
    try:
        from app.datagov.controls import control_service, exception_service  # type: ignore
        ctrls = await control_service.list_controls(db, tenant=tenant)
        out["controls_total"] = len(ctrls)
        by_status: dict[str, int] = {}
        for c in ctrls:
            s = getattr(c, "status", "UNKNOWN") or "UNKNOWN"
            by_status[s] = by_status.get(s, 0) + 1
        out["controls_by_status"] = by_status
        excs = await exception_service.list_exceptions(db, tenant=tenant, include_expired=False)
        out["exceptions_active"] = len(excs)
        # legal holds
        from app.datagov.models import GovernanceLegalHold  # type: ignore
        stmt2 = select(GovernanceLegalHold).where(GovernanceLegalHold.tenant == tenant, GovernanceLegalHold.released_at.is_(None))
        res2 = await db.execute(stmt2)
        holds = list(res2.scalars().all())
        out["legal_holds_active"] = len(holds)
        # dlp
        from app.datagov.models import GovernanceDLPEvent  # type: ignore
        stmt3 = select(GovernanceDLPEvent).where(GovernanceDLPEvent.tenant == tenant).order_by(GovernanceDLPEvent.created_at.desc()).limit(5)
        res3 = await db.execute(stmt3)
        dlp = list(res3.scalars().all())
        out["dlp_recent"] = [{"id": str(r.id), "action": r.action, "resource": r.resource, "created_at": r.created_at.isoformat() if r.created_at else None} for r in dlp]
        out["dlp_total"] = len(dlp)
    except Exception as exc:
        logger.debug("dashboard controls failed: %s", exc)
        out["controls_total"] = out.get("controls_total", 0)
    out["disclaimer"] = "governance dashboard — decision support only"
    return out
