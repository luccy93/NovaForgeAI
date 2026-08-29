"""Risk scoring — Volume 63.

Configurable risk: severity, confidence, exposure, asset_criticality, privilege, data_classification, region.
Risk is decision support, not proof of compromise.
"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.secops.models import SecOpsRiskSnapshot

SEVERITY_WEIGHT = {"INFO": 0.1, "LOW": 0.3, "MEDIUM": 0.5, "HIGH": 0.8, "CRITICAL": 1.0}
EXPOSURE_WEIGHT = {"unknown": 0.3, "internal": 0.2, "external": 0.8, "public": 1.0, "internet": 0.9}
CRITICALITY_WEIGHT = {"low": 0.2, "medium": 0.5, "high": 0.8, "critical": 1.0}
PRIVILEGE_WEIGHT = {"user": 0.3, "service": 0.5, "admin": 0.9, "root": 1.0, "break_glass": 1.0}
CLASSIFICATION_WEIGHT = {"public": 0.1, "internal": 0.3, "confidential": 0.6, "restricted": 0.9, "secret": 1.0}

def calculate_risk(
    severity: str = "MEDIUM",
    confidence: float = 0.5,
    exposure: str = "unknown",
    asset_criticality: str = "medium",
    privilege: str = "user",
    data_classification: str = "internal",
    region: str = "",
) -> float:
    sev_w = SEVERITY_WEIGHT.get(severity.upper(), 0.5)
    exp_w = EXPOSURE_WEIGHT.get(exposure.lower(), 0.3)
    crit_w = CRITICALITY_WEIGHT.get(asset_criticality.lower(), 0.5)
    priv_w = PRIVILEGE_WEIGHT.get(privilege.lower(), 0.3)
    class_w = CLASSIFICATION_WEIGHT.get(data_classification.lower(), 0.3)
    # weighted sum, configurable
    # severity 0.3, confidence 0.2, exposure 0.15, criticality 0.15, privilege 0.1, classification 0.1
    risk = (
        sev_w * 0.30 +
        confidence * 0.20 +
        exp_w * 0.15 +
        crit_w * 0.15 +
        priv_w * 0.10 +
        class_w * 0.10
    ) * 100
    return round(min(max(risk, 0), 100), 2)

async def create_risk_snapshot(db: AsyncSession, tenant: str, payload: dict) -> SecOpsRiskSnapshot:
    severity = (payload.get("severity") or "MEDIUM").upper()
    confidence = float(payload.get("confidence", 0.5))
    exposure = payload.get("exposure") or "unknown"
    asset_criticality = payload.get("asset_criticality") or "medium"
    privilege = payload.get("privilege") or "user"
    data_classification = payload.get("data_classification") or "internal"
    region = payload.get("region") or ""
    resource_type = payload.get("resource_type") or ""
    resource_id = payload.get("resource_id") or payload.get("resource") or ""
    risk_score = calculate_risk(severity, confidence, exposure, asset_criticality, privilege, data_classification, region)
    snap = SecOpsRiskSnapshot(
        tenant=tenant,
        resource_type=resource_type,
        resource_id=resource_id,
        risk_score=risk_score,
        severity=severity,
        confidence=confidence,
        exposure=exposure,
        asset_criticality=asset_criticality,
        privilege=privilege,
        data_classification=data_classification,
        region=region,
        inputs=payload,
        method_version="1.0",
        calculated_at=datetime.now(timezone.utc),
    )
    db.add(snap)
    await db.flush()
    return snap

async def get_latest_risk(db: AsyncSession, tenant: str, resource_type: str | None = None, resource_id: str | None = None) -> SecOpsRiskSnapshot | None:
    from sqlalchemy import select
    q = select(SecOpsRiskSnapshot).where(SecOpsRiskSnapshot.tenant == tenant).order_by(SecOpsRiskSnapshot.calculated_at.desc())
    if resource_type:
        q = q.where(SecOpsRiskSnapshot.resource_type == resource_type)
    if resource_id:
        q = q.where(SecOpsRiskSnapshot.resource_id == resource_id)
    res = await db.execute(q.limit(1))
    return res.scalar_one_or_none()
