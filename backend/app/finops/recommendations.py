"""Evidence-based cost recommendations — Volume 69 Commit 2.

Every rule must cite evidence (counts, amounts, pricing rows). Estimated
savings are computed only from recorded prices; when savings cannot be
derived reliably the recommendation is stored with savings NULL
(reported as UNKNOWN), never fabricated.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.finops.governed_common import ValidationError, _utcnow
from app.finops.governed_models import FinOpsAuditLog, FinOpsCostRecord
from app.finops.governed_models_c2 import FinOpsRecommendation
from app.finops.pricing import list_pricing_versions


def _serialize(row: FinOpsRecommendation) -> dict:
    return {
        "id": str(row.id),
        "tenant": row.tenant,
        "rec_type": row.rec_type,
        "title": row.title,
        "evidence": row.evidence or {},
        "estimated_savings_cents": row.estimated_savings_cents,
        "savings": "UNKNOWN" if row.estimated_savings_cents is None else row.estimated_savings_cents,
        "savings_known": row.savings_known,
        "confidence": row.confidence,
        "affected_resource": row.affected_resource or "",
        "risk": row.risk,
        "status": row.status,
    }


async def _recent_records(db: AsyncSession, tenant: str, days: int = 30) -> list[FinOpsCostRecord]:
    cutoff = _utcnow() - timedelta(days=days)
    return list((await db.execute(select(FinOpsCostRecord).where(
        FinOpsCostRecord.tenant == tenant, FinOpsCostRecord.occurred_at >= cutoff,
    ))).scalars().all())


async def generate_recommendations(db: AsyncSession, tenant: str, *, actor: str = "") -> dict:
    if not tenant:
        raise ValidationError("tenant required")
    records = await _recent_records(db, tenant)
    created: list[dict] = []

    def _add(rec_type: str, title: str, evidence: dict, savings: Optional[int],
             confidence: float, affected: str, risk: str = "LOW") -> None:
        row = FinOpsRecommendation(
            id=uuid.uuid4(), tenant=tenant, rec_type=rec_type, title=title,
            evidence=evidence, estimated_savings_cents=savings,
            savings_known=savings is not None, confidence=confidence,
            affected_resource=affected, risk=risk, status="OPEN",
        )
        db.add(row)
        created.append(row)

    # Rule 1: dominant model with a cheaper priced sibling available.
    by_model: dict[str, int] = {}
    for record in records:
        if record.model:
            by_model[record.model] = by_model.get(record.model, 0) + (record.amount_cents or 0)
    total = sum(by_model.values())
    if total > 0:
        top_model, top_spend = max(by_model.items(), key=lambda kv: kv[1])
        if top_spend / total >= 0.5:
            versions = await list_pricing_versions(db, tenant, status="ACTIVE")
            top_rates = [v for v in versions if v["model"] == top_model]
            top_rate = min(
                [v["input_price_cents_per_m"] + v["output_price_cents_per_m"] for v in top_rates] or [0]
            )
            cheaper = [v for v in versions
                       if (v["input_price_cents_per_m"] + v["output_price_cents_per_m"]) < top_rate]
            evidence = {"top_model": top_model, "top_spend_cents": top_spend,
                        "total_cents": total, "share": round(top_spend / total, 4),
                        "cheaper_models": [f"{v['provider']}/{v['model']}" for v in cheaper[:5]]}
            if cheaper and top_rate > 0:
                best = min(cheaper, key=lambda v: v["input_price_cents_per_m"] + v["output_price_cents_per_m"])
                best_rate = best["input_price_cents_per_m"] + best["output_price_cents_per_m"]
                savings = int(round(top_spend * (1 - best_rate / top_rate)))
                _add("cheaper_model", f"Consider {best['provider']}/{best['model']} for {top_model} workloads",
                     {**evidence, "recommended": f"{best['provider']}/{best['model']}"},
                     savings, 0.6, f"model:{top_model}", risk="MEDIUM")
            else:
                _add("model_concentration", f"{top_model} dominates spend ({round(top_spend/total*100, 1)}%)",
                     evidence, None, 0.5, f"model:{top_model}")

    # Rule 2: high request volume with tiny payloads -> batching opportunity, savings unknown.
    op_stats: dict[tuple[str, str], dict] = {}
    for record in records:
        key = (record.model or "", record.operation or "")
        cell = op_stats.setdefault(key, {"requests": 0, "tokens": 0})
        cell["requests"] += record.requests or 0
        cell["tokens"] += (record.input_tokens or 0) + (record.output_tokens or 0)
    for (model, operation), stats in op_stats.items():
        if stats["requests"] >= 50 and stats["requests"] > 0 and (stats["tokens"] / stats["requests"]) < 200:
            _add("batch_requests", f"Batch small {operation or 'unnamed'} requests on {model or 'unknown model'}",
                 {"model": model, "operation": operation, "requests": stats["requests"],
                  "avg_tokens_per_request": round(stats["tokens"] / stats["requests"], 1)},
                 None, 0.4, f"model:{model}", risk="LOW")

    # Rule 3: unpriced records -> pricing coverage gap, savings unknown.
    unpriced = [r for r in records if r.cost_basis == "unpriced"]
    if unpriced:
        providers = sorted({r.provider for r in unpriced if r.provider})
        _add("pricing_coverage", f"{len(unpriced)} records lack pricing",
             {"unpriced_count": len(unpriced), "providers": providers},
             None, 0.7, "pricing", risk="LOW")

    for row in created:
        await db.flush()
    if created:
        db.add(FinOpsAuditLog(
            tenant=tenant, actor=actor or "", action="recommendation.generate",
            resource_type="recommendation", resource_id="",
            details={"generated": len(created)}, status="SUCCESS",
        ))
        await db.flush()
        try:
            from app.finops.governed_events import recommendation_created
            for row in created:
                await recommendation_created(tenant, {"id": str(row.id), "rec_type": row.rec_type})
        except Exception:
            pass
    return {"recommendations": [_serialize(r) for r in created], "total": len(created)}


async def list_recommendations(db: AsyncSession, tenant: str, *, rec_type: str = "", status: str = "", limit: int = 100) -> dict:
    stmt = select(FinOpsRecommendation).where(FinOpsRecommendation.tenant == tenant)
    if rec_type:
        stmt = stmt.where(FinOpsRecommendation.rec_type == rec_type)
    if status:
        stmt = stmt.where(FinOpsRecommendation.status == status)
    limit = min(max(int(limit or 100), 1), 1000)
    rows = (await db.execute(stmt.order_by(desc(FinOpsRecommendation.created_at)).limit(limit))).scalars().all()
    return {"items": [_serialize(r) for r in rows], "total": len(rows)}
