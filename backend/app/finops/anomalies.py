"""Bounded statistical anomaly detection — Volume 69 Commit 2.

Per-dimension daily spend is compared against its own rolling baseline
using z-scores. Detections are deduplicated on
(tenant, dimension, bucket) so retries and repeated runs cannot create
alert storms. Every anomaly carries baseline, observed value, deviation,
severity, confidence and its evidence window.
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.finops.governed_common import (
    ValidationError,
    _ensure_aware,
    _utcnow,
    parse_time,
)
from app.finops.governed_models import FinOpsCostRecord
from app.finops.governed_models_c2 import FinOpsAnomaly

DIMENSION_KEYS = ("provider", "model", "workspace", "project", "service", "operation")
BASELINE_DAYS = 13
Z_MEDIUM = 2.0
Z_HIGH = 3.0
Z_CRITICAL = 4.0


def _serialize(row: FinOpsAnomaly) -> dict:
    return {
        "id": str(row.id),
        "tenant": row.tenant,
        "dimension_key": row.dimension_key,
        "dimension_value": row.dimension_value or "",
        "granularity": row.granularity,
        "bucket_start": row.bucket_start.isoformat() if row.bucket_start else None,
        "baseline_cents": row.baseline_cents,
        "observed_cents": row.observed_cents,
        "deviation": row.deviation,
        "severity": row.severity,
        "confidence": row.confidence,
        "evidence": row.evidence or {},
        "status": row.status,
    }


def _severity(z: float) -> str:
    az = abs(z)
    if az >= Z_CRITICAL:
        return "CRITICAL"
    if az >= Z_HIGH:
        return "HIGH"
    if az >= Z_MEDIUM:
        return "MEDIUM"
    return "LOW"


async def detect_anomalies(
    db: AsyncSession, tenant: str, *, lookback_days: int = 14, min_baseline_cents: int = 1, actor: str = "",
) -> dict:
    if not tenant:
        raise ValidationError("tenant required")
    lookback_days = min(max(int(lookback_days or 14), 7), 60)
    end = _utcnow()
    start = end - timedelta(days=lookback_days)
    records = (await db.execute(select(FinOpsCostRecord).where(
        FinOpsCostRecord.tenant == tenant,
        FinOpsCostRecord.occurred_at >= start,
        FinOpsCostRecord.occurred_at <= end,
    ))).scalars().all()

    # series[(dim_key, dim_value, day)] = cents
    series: dict[tuple[str, str, str], int] = {}
    for record in records:
        day = _ensure_aware(record.occurred_at).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        for key in DIMENSION_KEYS:
            value = str(getattr(record, key, "") or "")
            if not value:
                continue
            cell = (key, value, day)
            series[cell] = series.get(cell, 0) + (record.amount_cents or 0)

    # group by (dim_key, dim_value) -> sorted [(day, total)]
    grouped: dict[tuple[str, str], list[tuple[str, int]]] = {}
    for (key, value, day), total in series.items():
        grouped.setdefault((key, value), []).append((day, total))
    created: list[dict] = []
    for (key, value), points in grouped.items():
        points.sort()
        if len(points) < 5:
            continue
        *history, (last_day, observed) = points
        baseline_vals = [total for _, total in history]
        mean = sum(baseline_vals) / len(baseline_vals)
        if mean < min_baseline_cents:
            continue
        variance = sum((v - mean) ** 2 for v in baseline_vals) / len(baseline_vals)
        std = math.sqrt(variance)
        if std == 0:
            z = 0.0 if observed == mean else 5.0
        else:
            z = (observed - mean) / std
        if abs(z) < Z_MEDIUM:
            continue
        bucket = datetime.fromisoformat(last_day)
        dup = (await db.execute(select(FinOpsAnomaly).where(
            FinOpsAnomaly.tenant == tenant, FinOpsAnomaly.dimension_key == key,
            FinOpsAnomaly.dimension_value == value, FinOpsAnomaly.bucket_start == bucket,
        ))).scalar_one_or_none()
        if dup is not None:
            created.append({**_serialize(dup), "deduplicated": True})
            continue
        row = FinOpsAnomaly(
            id=uuid.uuid4(), tenant=tenant, dimension_key=key, dimension_value=value,
            granularity="day", bucket_start=bucket,
            baseline_cents=int(round(mean)), observed_cents=int(observed),
            deviation=round(z, 4), severity=_severity(z),
            confidence=round(min(abs(z) / 5.0, 0.95), 4),
            evidence={"window_days": lookback_days, "window_start": start.isoformat(),
                      "window_end": end.isoformat(), "history": baseline_vals[-BASELINE_DAYS:]},
            status="OPEN",
        )
        db.add(row)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            continue
        created.append(_serialize(row))
        try:
            from app.finops.governed_events import anomaly_detected
            await anomaly_detected(tenant, {"id": str(row.id), "severity": row.severity,
                                            "dimension": f"{key}={value}", "deviation": row.deviation})
        except Exception:
            pass
    return {"anomalies": created, "total": len(created)}


async def list_anomalies(db: AsyncSession, tenant: str, *, severity: str = "", status: str = "", limit: int = 100) -> dict:
    stmt = select(FinOpsAnomaly).where(FinOpsAnomaly.tenant == tenant)
    if severity:
        stmt = stmt.where(FinOpsAnomaly.severity == severity)
    if status:
        stmt = stmt.where(FinOpsAnomaly.status == status)
    limit = min(max(int(limit or 100), 1), 1000)
    rows = (await db.execute(stmt.order_by(desc(FinOpsAnomaly.created_at)).limit(limit))).scalars().all()
    return {"items": [_serialize(r) for r in rows], "total": len(rows)}
