"""Governed FinOps event emitters — Volume 69 Commit 1.

Thin wrappers over the existing EventBus. All emission is best-effort;
financial state never depends on delivery.
"""

from __future__ import annotations

from typing import Optional

from app.finops.governed_common import emit_finops_event


async def usage_recorded(tenant: str, record: dict) -> None:
    await emit_finops_event("finops_usage_recorded", {"record": record}, tenant)


async def cost_calculated(tenant: str, record: dict) -> None:
    await emit_finops_event("finops_cost_calculated", {"record": record}, tenant)


async def budget_warning(tenant: str, budget_id: str, spend_cents: int, threshold: float) -> None:
    await emit_finops_event(
        "finops_budget_warning",
        {"budget_id": budget_id, "spend_cents": spend_cents, "threshold": threshold},
        tenant,
    )


async def budget_exceeded(tenant: str, budget_id: str, spend_cents: int, threshold: float) -> None:
    await emit_finops_event(
        "finops_budget_exceeded",
        {"budget_id": budget_id, "spend_cents": spend_cents, "threshold": threshold},
        tenant,
    )


async def allocation_completed(tenant: str, cost_record_id: str, count: int) -> None:
    await emit_finops_event(
        "finops_allocation_completed",
        {"cost_record_id": cost_record_id, "allocation_count": count},
        tenant,
    )


async def forecast_generated(tenant: str, forecast: dict) -> None:
    await emit_finops_event("finops_forecast_generated", {"forecast": forecast}, tenant)


async def anomaly_detected(tenant: str, anomaly: dict) -> None:
    await emit_finops_event("finops_anomaly_detected", {"anomaly": anomaly}, tenant)


async def recommendation_created(tenant: str, recommendation: dict) -> None:
    await emit_finops_event("finops_recommendation_created", {"recommendation": recommendation}, tenant)


async def policy_decision(tenant: str, decision: dict) -> None:
    await emit_finops_event("finops_policy_decision", {"decision": decision}, tenant)


async def chargeback_generated(tenant: str, report: dict) -> None:
    await emit_finops_event("finops_chargeback_generated", {"report": report}, tenant)
