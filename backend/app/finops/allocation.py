"""Deterministic cost allocation — Volume 69 Commit 1.

Attribution of a cost record to target dimensions (workspace/project/
service/environment). Allocation is idempotent on
(tenant, cost_record_id, allocation_key): worker retries return existing
rows instead of double counting. Shares must sum to ~1.0.
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.finops.governed_common import NotFoundError, ValidationError, sanitize_metadata
from app.finops.governed_models import FinOpsAuditLog, FinOpsCostAllocation, FinOpsCostRecord


def _serialize(row: FinOpsCostAllocation) -> dict:
    return {
        "id": str(row.id),
        "tenant": row.tenant,
        "cost_record_id": str(row.cost_record_id),
        "allocation_key": row.allocation_key,
        "target_workspace": row.target_workspace or "",
        "target_project": row.target_project or "",
        "target_service": row.target_service or "",
        "target_environment": row.target_environment or "",
        "share": row.share,
        "amount_cents": row.amount_cents,
        "basis": row.basis,
    }


async def allocate_cost(
    db: AsyncSession, tenant: str, cost_record_id, splits: list[dict], *, actor: str = "", basis: str = "direct",
) -> list[dict]:
    if not tenant:
        raise ValidationError("tenant required")
    if not splits:
        raise ValidationError("splits required")
    from app.finops.governed_common import _as_uuid
    stmt = select(FinOpsCostRecord).where(FinOpsCostRecord.id == _as_uuid(cost_record_id), FinOpsCostRecord.tenant == tenant)
    record = (await db.execute(stmt)).scalar_one_or_none()
    if record is None:
        raise NotFoundError("cost record not found")

    total_share = sum(float(s.get("share", 0)) for s in splits)
    if abs(total_share - 1.0) > 0.001:
        raise ValidationError(f"splits must sum to 1.0 (got {total_share})")

    created: list[dict] = []
    for split in splits:
        key = str(split.get("allocation_key") or "").strip()
        if not key:
            raise ValidationError("allocation_key required per split")
        share = float(split.get("share", 0))
        if share < 0 or share > 1:
            raise ValidationError("share must be in [0, 1]")
        amount = int(round(record.amount_cents * share))
        row = FinOpsCostAllocation(
            id=uuid.uuid4(), tenant=tenant, cost_record_id=record.id, allocation_key=key,
            target_workspace=str(split.get("target_workspace") or ""),
            target_project=str(split.get("target_project") or ""),
            target_service=str(split.get("target_service") or ""),
            target_environment=str(split.get("target_environment") or ""),
            share=share, amount_cents=amount, basis=basis,
            metadata_=sanitize_metadata(split.get("metadata")),
        )
        try:
            async with db.begin_nested():
                db.add(row)
                await db.flush()
        except IntegrityError:
            existing_stmt = select(FinOpsCostAllocation).where(
                FinOpsCostAllocation.tenant == tenant,
                FinOpsCostAllocation.cost_record_id == record.id,
                FinOpsCostAllocation.allocation_key == key,
            )
            existing = (await db.execute(existing_stmt)).scalar_one_or_none()
            if existing is None:
                raise
            created.append({**_serialize(existing), "deduplicated": True})
            continue
        created.append(_serialize(row))

    db.add(FinOpsAuditLog(
        tenant=tenant, actor=actor or "", action="cost.allocate",
        resource_type="cost_record", resource_id=str(record.id),
        details={"allocation_count": len(created), "basis": basis}, status="SUCCESS",
    ))
    await db.flush()
    try:
        from app.finops.governed_events import allocation_completed
        await allocation_completed(tenant, str(record.id), len(created))
    except Exception:
        pass
    return created


async def list_allocations(db: AsyncSession, tenant: str, *, cost_record_id=None, limit: int = 100, offset: int = 0) -> dict:
    from app.finops.governed_common import _as_uuid
    stmt = select(FinOpsCostAllocation).where(FinOpsCostAllocation.tenant == tenant)
    if cost_record_id:
        stmt = stmt.where(FinOpsCostAllocation.cost_record_id == _as_uuid(cost_record_id))
    limit = min(max(int(limit or 100), 1), 1000)
    offset = max(int(offset or 0), 0)
    rows = (await db.execute(stmt.order_by(desc(FinOpsCostAllocation.created_at)).limit(limit).offset(offset))).scalars().all()
    return {"items": [_serialize(r) for r in rows], "total": len(rows), "limit": limit, "offset": offset}
