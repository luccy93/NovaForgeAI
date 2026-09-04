"""Chargeback and showback reporting — Volume 69 Commit 2.

SHOWBACK is informational attribution from governed cost records.
CHARGEBACK is governed financial attribution sourced from allocation
rows, so every charged cent traces to an allocation with provenance.
No double counting: each source row contributes once per report.
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.finops.governed_common import ValidationError, _ensure_aware, clamp_range, parse_time
from app.finops.governed_models import FinOpsAuditLog, FinOpsCostAllocation, FinOpsCostRecord
from app.finops.governed_models_c2 import FinOpsChargebackReport

REPORT_TYPES = ("showback", "chargeback")
GROUP_KEYS = ("workspace", "project", "service", "environment", "provider", "model")


def _serialize(row: FinOpsChargebackReport) -> dict:
    return {
        "id": str(row.id),
        "tenant": row.tenant,
        "report_type": row.report_type,
        "period_start": row.period_start.isoformat() if row.period_start else None,
        "period_end": row.period_end.isoformat() if row.period_end else None,
        "scope": row.scope or {},
        "total_cents": row.total_cents,
        "lines": row.lines or [],
        "provenance": row.provenance or {},
    }


async def generate_report(
    db: AsyncSession, tenant: str, report_type: str, *,
    start=None, end=None, group_by: str = "workspace", actor: str = "",
) -> dict:
    if not tenant:
        raise ValidationError("tenant required")
    if report_type not in REPORT_TYPES:
        raise ValidationError(f"unsupported report type: {report_type!r}")
    if group_by not in GROUP_KEYS:
        raise ValidationError(f"unsupported group_by: {group_by!r}")
    start, end = clamp_range(parse_time(start), parse_time(end))

    lines: list[dict] = []
    total = 0
    provenance: dict = {"report_type": report_type}
    if report_type == "showback":
        records = (await db.execute(select(FinOpsCostRecord).where(
            FinOpsCostRecord.tenant == tenant,
            FinOpsCostRecord.occurred_at >= start,
            FinOpsCostRecord.occurred_at <= end,
        ))).scalars().all()
        grouped: dict[str, dict] = {}
        for record in records:
            key = str(getattr(record, group_by, "") or "(unattributed)")
            cell = grouped.setdefault(key, {"group": key, "total_cents": 0, "record_count": 0})
            cell["total_cents"] += record.amount_cents or 0
            cell["record_count"] += 1
            total += record.amount_cents or 0
        lines = sorted(grouped.values(), key=lambda c: c["total_cents"], reverse=True)
        provenance["source"] = "finops_cost_records"
        provenance["record_count"] = len(records)
    else:
        allocations = (await db.execute(select(FinOpsCostAllocation).where(
            FinOpsCostAllocation.tenant == tenant,
        ))).scalars().all()
        # Join period via parent cost records.
        parent_ids = list({a.cost_record_id for a in allocations})
        in_period: set[str] = set()
        for pid in parent_ids:
            parent = await db.get(FinOpsCostRecord, pid)
            if parent is not None and parent.tenant == tenant and start <= _ensure_aware(parent.occurred_at) <= end:
                in_period.add(str(pid))
        grouped = {}
        count = 0
        for allocation in allocations:
            if str(allocation.cost_record_id) not in in_period:
                continue
            if group_by == "workspace":
                key = allocation.target_workspace or "(unattributed)"
            elif group_by == "project":
                key = allocation.target_project or "(unattributed)"
            elif group_by == "service":
                key = allocation.target_service or "(unattributed)"
            elif group_by == "environment":
                key = allocation.target_environment or "(unattributed)"
            else:
                parent = await db.get(FinOpsCostRecord, allocation.cost_record_id)
                key = str(getattr(parent, group_by, "") or "(unattributed)") if parent else "(unattributed)"
            cell = grouped.setdefault(key, {"group": key, "total_cents": 0, "allocation_count": 0})
            cell["total_cents"] += allocation.amount_cents or 0
            cell["allocation_count"] += 1
            total += allocation.amount_cents or 0
            count += 1
        lines = sorted(grouped.values(), key=lambda c: c["total_cents"], reverse=True)
        provenance["source"] = "finops_cost_allocations"
        provenance["allocation_count"] = count

    row = FinOpsChargebackReport(
        id=uuid.uuid4(), tenant=tenant, report_type=report_type,
        period_start=start, period_end=end,
        scope={"group_by": group_by}, total_cents=total,
        lines=lines, provenance=provenance,
    )
    try:
        async with db.begin_nested():
            db.add(row)
            await db.flush()
    except IntegrityError:
        dup = (await db.execute(select(FinOpsChargebackReport).where(
            FinOpsChargebackReport.tenant == tenant,
            FinOpsChargebackReport.report_type == report_type,
            FinOpsChargebackReport.period_start == start,
            FinOpsChargebackReport.period_end == end,
        ))).scalar_one_or_none()
        if dup is None:
            raise
        return {**_serialize(dup), "deduplicated": True}

    db.add(FinOpsAuditLog(
        tenant=tenant, actor=actor or "", action=f"{report_type}.generate",
        resource_type="report", resource_id=str(row.id),
        details={"total_cents": total, "group_by": group_by}, status="SUCCESS",
    ))
    await db.flush()
    try:
        from app.finops.governed_events import chargeback_generated
        await chargeback_generated(tenant, {"id": str(row.id), "report_type": report_type, "total_cents": total})
    except Exception:
        pass
    return _serialize(row)


async def list_reports(db: AsyncSession, tenant: str, *, report_type: str = "", limit: int = 50) -> dict:
    stmt = select(FinOpsChargebackReport).where(FinOpsChargebackReport.tenant == tenant)
    if report_type:
        stmt = stmt.where(FinOpsChargebackReport.report_type == report_type)
    limit = min(max(int(limit or 50), 1), 1000)
    rows = (await db.execute(stmt.order_by(desc(FinOpsChargebackReport.created_at)).limit(limit))).scalars().all()
    return {"items": [_serialize(r) for r in rows], "total": len(rows)}
