"""Versioned pricing — Volume 69 Commit 1.

Pricing versions are immutable history. New prices create new versions;
existing rows are never mutated except for authorized status transitions
(ACTIVE <-> DEPRECATED). Historical cost records keep the pricing version
that was effective for their usage plus a snapshot of applied rates.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import and_, desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.finops.governed_common import (
    NotFoundError,
    ValidationError,
    _ensure_aware,
    _utcnow,
    parse_time,
    sanitize_metadata,
)
from app.finops.governed_models import FinOpsAuditLog, FinOpsPricingVersion

ALLOWED_STATUSES = ("ACTIVE", "DEPRECATED")


def _serialize(row: FinOpsPricingVersion) -> dict:
    return {
        "id": str(row.id),
        "tenant": row.tenant,
        "provider": row.provider,
        "model": row.model,
        "resource": row.resource or "",
        "unit": row.unit,
        "input_price_cents_per_m": row.input_price_cents_per_m,
        "output_price_cents_per_m": row.output_price_cents_per_m,
        "request_price_cents": row.request_price_cents,
        "storage_price_cents": row.storage_price_cents,
        "compute_price_cents": row.compute_price_cents,
        "currency": row.currency,
        "effective_from": row.effective_from.isoformat() if row.effective_from else None,
        "effective_until": row.effective_until.isoformat() if row.effective_until else None,
        "source": row.source,
        "version": row.version,
        "status": row.status,
        "operator": row.operator,
        "reason": row.reason,
    }


async def _audit(db: AsyncSession, tenant: str, actor: str, action: str, resource_id: str, details: dict) -> None:
    db.add(FinOpsAuditLog(
        tenant=tenant, actor=actor or "", action=action,
        resource_type="pricing_version", resource_id=resource_id,
        details=sanitize_metadata(details), status="SUCCESS",
    ))
    await db.flush()


async def create_pricing_version(
    db: AsyncSession,
    tenant: str,
    provider: str,
    *,
    model: str = "",
    resource: str = "",
    unit: str = "tokens",
    input_price_cents_per_m: float = 0.0,
    output_price_cents_per_m: float = 0.0,
    request_price_cents: float = 0.0,
    storage_price_cents: float = 0.0,
    compute_price_cents: float = 0.0,
    currency: str = "USD",
    effective_from=None,
    effective_until=None,
    source: str = "manual",
    operator: str = "",
    reason: str = "",
    metadata: Optional[dict] = None,
) -> dict:
    provider = (provider or "").strip()
    if not provider:
        raise ValidationError("provider required")
    if any(v < 0 for v in (input_price_cents_per_m, output_price_cents_per_m, request_price_cents, storage_price_cents, compute_price_cents)):
        raise ValidationError("prices must be >= 0")
    eff_from = _ensure_aware(parse_time(effective_from) or _utcnow())
    eff_until = _ensure_aware(parse_time(effective_until)) if effective_until else None
    if eff_until and eff_until <= eff_from:
        raise ValidationError("effective_until must be after effective_from")

    stmt = select(func.max(FinOpsPricingVersion.version)).where(
        FinOpsPricingVersion.tenant == tenant,
        FinOpsPricingVersion.provider == provider,
        FinOpsPricingVersion.model == (model or ""),
        FinOpsPricingVersion.unit == unit,
    )
    max_version = (await db.execute(stmt)).scalar() or 0

    row = FinOpsPricingVersion(
        id=uuid.uuid4(), tenant=tenant, provider=provider, model=model or "",
        resource=resource or "", unit=unit,
        input_price_cents_per_m=float(input_price_cents_per_m),
        output_price_cents_per_m=float(output_price_cents_per_m),
        request_price_cents=float(request_price_cents),
        storage_price_cents=float(storage_price_cents),
        compute_price_cents=float(compute_price_cents),
        currency=(currency or "USD").upper(),
        effective_from=eff_from, effective_until=eff_until,
        source=source or "manual", version=int(max_version) + 1, status="ACTIVE",
        operator=operator or "", reason=reason or "",
        metadata_=sanitize_metadata(metadata),
    )
    db.add(row)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ValidationError("pricing version already exists")
    await _audit(db, tenant, operator, "pricing.create", str(row.id), {"provider": provider, "model": model, "version": row.version})
    return _serialize(row)


async def list_pricing_versions(
    db: AsyncSession, tenant: str, *, provider: str = "", model: str = "", status: str = "", limit: int = 100,
) -> list[dict]:
    stmt = select(FinOpsPricingVersion).where(FinOpsPricingVersion.tenant == tenant)
    if provider:
        stmt = stmt.where(FinOpsPricingVersion.provider == provider)
    if model:
        stmt = stmt.where(FinOpsPricingVersion.model == model)
    if status:
        stmt = stmt.where(FinOpsPricingVersion.status == status)
    rows = (await db.execute(stmt.order_by(desc(FinOpsPricingVersion.version)).limit(min(max(limit, 1), 1000)))).scalars().all()
    return [_serialize(r) for r in rows]


async def get_effective_pricing(
    db: AsyncSession, tenant: str, provider: str, *, model: str = "", unit: str = "tokens", at=None,
) -> Optional[dict]:
    """Return the ACTIVE pricing version effective at `at` (highest version wins)."""
    moment = _ensure_aware(parse_time(at) or _utcnow())
    stmt = (
        select(FinOpsPricingVersion)
        .where(
            FinOpsPricingVersion.tenant == tenant,
            FinOpsPricingVersion.provider == provider,
            FinOpsPricingVersion.model == (model or ""),
            FinOpsPricingVersion.unit == unit,
            FinOpsPricingVersion.status == "ACTIVE",
            FinOpsPricingVersion.effective_from <= moment,
            ((FinOpsPricingVersion.effective_until.is_(None)) | (FinOpsPricingVersion.effective_until > moment)),
        )
        .order_by(desc(FinOpsPricingVersion.version))
        .limit(1)
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    return _serialize(row) if row else None


async def deprecate_pricing_version(db: AsyncSession, tenant: str, version_id, *, operator: str = "", reason: str = "") -> dict:
    from app.finops.governed_common import _as_uuid
    stmt = select(FinOpsPricingVersion).where(FinOpsPricingVersion.id == _as_uuid(version_id), FinOpsPricingVersion.tenant == tenant)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise NotFoundError("pricing version not found")
    row.status = "DEPRECATED"
    if reason:
        row.reason = reason
    await db.flush()
    await _audit(db, tenant, operator, "pricing.deprecate", str(row.id), {"version": row.version, "reason": reason})
    return _serialize(row)
