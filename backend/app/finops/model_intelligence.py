"""Provider/model cost intelligence — Volume 69 Commit 2.

Read-only comparisons from recorded costs and effective pricing:
spend, cost per request, token efficiency and latency. FinOps never
switches models; switching stays governed by the AI Gateway and policy
controls.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.finops.governed_common import ValidationError, _utcnow, clamp_range, parse_time
from app.finops.governed_models import FinOpsCostRecord
from app.finops.pricing import get_effective_pricing


async def compare_models(
    db: AsyncSession, tenant: str, *, start=None, end=None, provider: str = "",
) -> dict:
    if not tenant:
        raise ValidationError("tenant required")
    start_p, end_p = clamp_range(parse_time(start), parse_time(end)) if (start or end) else (None, None)
    if start_p is None:
        end_p = _utcnow()
        start_p = end_p - timedelta(days=30)
    stmt = select(FinOpsCostRecord).where(
        FinOpsCostRecord.tenant == tenant,
        FinOpsCostRecord.occurred_at >= start_p,
        FinOpsCostRecord.occurred_at <= end_p,
    )
    if provider:
        stmt = stmt.where(FinOpsCostRecord.provider == provider)
    records = (await db.execute(stmt)).scalars().all()

    grouped: dict[tuple[str, str], dict] = {}
    for record in records:
        key = (record.provider or "", record.model or "")
        cell = grouped.setdefault(key, {"spend_cents": 0, "requests": 0, "tokens": 0, "latency_sum": 0, "latency_n": 0})
        cell["spend_cents"] += record.amount_cents or 0
        cell["requests"] += record.requests or 0
        cell["tokens"] += (record.input_tokens or 0) + (record.output_tokens or 0)
        if record.latency_ms is not None:
            cell["latency_sum"] += record.latency_ms
            cell["latency_n"] += 1

    rows: list[dict] = []
    for (prov, model), stats in grouped.items():
        pricing = await get_effective_pricing(db, tenant, prov, model=model) if prov else None
        requests = stats["requests"] or 0
        rows.append({
            "provider": prov, "model": model,
            "spend_cents": stats["spend_cents"],
            "requests": requests,
            "tokens": stats["tokens"],
            "cost_per_request_cents": round(stats["spend_cents"] / requests, 4) if requests else None,
            "tokens_per_request": round(stats["tokens"] / requests, 1) if requests else None,
            "avg_latency_ms": round(stats["latency_sum"] / stats["latency_n"], 1) if stats["latency_n"] else None,
            "input_price_cents_per_m": pricing.get("input_price_cents_per_m") if pricing else None,
            "output_price_cents_per_m": pricing.get("output_price_cents_per_m") if pricing else None,
            "pricing_version": pricing.get("version") if pricing else None,
        })
    rows.sort(key=lambda r: r["spend_cents"], reverse=True)
    return {"items": rows, "total": len(rows),
            "start": start_p.isoformat(), "end": end_p.isoformat(),
            "note": "comparison only; model selection remains governed by AI Gateway policy"}
