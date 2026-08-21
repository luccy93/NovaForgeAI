"""NovaForge Analytics Platform -- Recommendation Service (Volume 50).

In-memory recommendation engine for cost and usage optimization.
Recommendations are strictly advisory: every record carries a reason,
supporting evidence, an estimated impact, a confidence score, a risk
level and a suggested action. Nothing is ever executed automatically.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

STATUS_PENDING = "pending"
STATUS_ACCEPTED = "accepted"
STATUS_DISMISSED = "dismissed"

RISK_LEVELS = ("low", "medium", "high")
PRIORITY_LEVELS = ("low", "medium", "high", "critical")

COST_SPIKE_RATIO = 0.30
COST_SPIKE_MIN_USD = 50.0
IDLE_UTILIZATION_PCT = 5.0
UNDERUTILIZED_UTILIZATION_PCT = 30.0
CONCENTRATION_SHARE = 0.60
CONCENTRATION_MIN_TOTAL_USD = 1000.0


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RecommendationService:
    """Generates and tracks advisory optimization recommendations."""

    def __init__(self):
        self._recommendations: dict[str, dict] = {}

    # ── Generation ─────────────────────────────────────────────────────

    def generate_recommendations(self, tenant: str, data: dict | None = None) -> list[dict]:
        """Analyze cost/usage data and record advisory recommendations.

        Expected ``data`` shape (all keys optional):
            {
              "cost_by_service": {"<service>": {"current_month_usd": x,
                                                "previous_month_usd": y}},
              "resources": [{"resource_id": str, "resource_type": str,
                             "monthly_cost_usd": float,
                             "utilization_pct": float}],
              "total_monthly_cost_usd": float
            }
        """
        data = data or {}
        created: list[dict] = []
        cost_by_service = data.get("cost_by_service") or {}
        resources = data.get("resources") or []
        total_cost = data.get("total_monthly_cost_usd")
        if not isinstance(total_cost, (int, float)) or total_cost <= 0:
            total_cost = sum(
                float((values or {}).get("current_month_usd", 0.0))
                for values in cost_by_service.values()
            )
        for service, values in cost_by_service.items():
            values = values or {}
            current = float(values.get("current_month_usd", 0.0))
            previous = float(values.get("previous_month_usd", 0.0))
            if previous <= 0 or current <= previous:
                continue
            increase = current - previous
            ratio = increase / previous
            if ratio < COST_SPIKE_RATIO or increase < COST_SPIKE_MIN_USD:
                continue
            priority = "high" if (ratio >= 1.0 or increase >= 500.0) else "medium"
            created.append(self.record_recommendation(
                tenant=tenant,
                category="cost_optimization",
                title=f"Cost spike detected for {service}",
                description=(f"Monthly spend for '{service}' rose from "
                             f"${previous:.2f} to ${current:.2f}."),
                reason=(f"'{service}' spend increased {ratio:.0%} "
                        f"(${increase:.2f}) period over period."),
                evidence={"service": service,
                          "previous_month_usd": round(previous, 2),
                          "current_month_usd": round(current, 2),
                          "increase_usd": round(increase, 2),
                          "increase_ratio": round(ratio, 4)},
                estimated_impact_usd=round(increase, 2),
                confidence=0.7,
                risk="low",
                priority=priority,
                suggested_action=(f"Investigate recent usage changes for '{service}' "
                                  "and confirm whether the increase is expected "
                                  "before making any changes.")))
        for resource in resources:
            resource = resource or {}
            utilization = float(resource.get("utilization_pct", 0.0))
            monthly_cost = float(resource.get("monthly_cost_usd", 0.0))
            resource_id = str(resource.get("resource_id", ""))
            resource_type = str(resource.get("resource_type", "compute"))
            if not resource_id or monthly_cost <= 0:
                continue
            if utilization <= IDLE_UTILIZATION_PCT:
                created.append(self.record_recommendation(
                    tenant=tenant,
                    category="resource_management",
                    title=f"Idle resource: {resource_id}",
                    description=(f"'{resource_id}' ({resource_type}) shows "
                                 f"{utilization:.1f}% utilization at "
                                 f"${monthly_cost:.2f}/month."),
                    reason=(f"'{resource_id}' is effectively idle "
                            f"({utilization:.1f}% utilization) while costing "
                            f"${monthly_cost:.2f} per month."),
                    evidence={"resource_id": resource_id,
                              "resource_type": resource_type,
                              "utilization_pct": utilization,
                              "monthly_cost_usd": round(monthly_cost, 2)},
                    estimated_impact_usd=round(monthly_cost, 2),
                    confidence=0.85,
                    risk="medium",
                    priority="high" if monthly_cost >= 200.0 else "medium",
                    suggested_action=(f"Verify '{resource_id}' is not required for batch "
                                      "or seasonal workloads, then decommission it.")))
            elif utilization < UNDERUTILIZED_UTILIZATION_PCT and monthly_cost >= 20.0:
                created.append(self.record_recommendation(
                    tenant=tenant,
                    category="resource_management",
                    title=f"Underutilized resource: {resource_id}",
                    description=(f"'{resource_id}' ({resource_type}) runs at "
                                 f"{utilization:.1f}% utilization."),
                    reason=(f"'{resource_id}' is consistently underutilized "
                            f"({utilization:.1f}%), indicating it is oversized "
                            f"for its workload (${monthly_cost:.2f}/month)."),
                    evidence={"resource_id": resource_id,
                              "resource_type": resource_type,
                              "utilization_pct": utilization,
                              "monthly_cost_usd": round(monthly_cost, 2)},
                    estimated_impact_usd=round(monthly_cost * 0.4, 2),
                    confidence=0.6,
                    risk="low",
                    priority="medium",
                    suggested_action=(f"Downsize '{resource_id}' to a smaller size "
                                      "matched to its observed utilization.")))
        if total_cost >= CONCENTRATION_MIN_TOTAL_USD and cost_by_service:
            top_service = max(cost_by_service,
                              key=lambda name: float((cost_by_service[name] or {}).get(
                                  "current_month_usd", 0.0)))
            top_value = float((cost_by_service[top_service] or {}).get(
                "current_month_usd", 0.0))
            share = top_value / total_cost if total_cost else 0.0
            if share >= CONCENTRATION_SHARE:
                created.append(self.record_recommendation(
                    tenant=tenant,
                    category="capacity_planning",
                    title=f"Spend concentrated in {top_service}",
                    description=(f"'{top_service}' accounts for {share:.0%} of "
                                 f"total monthly spend."),
                    reason=(f"{share:.0%} of the ${total_cost:.2f} monthly total "
                            f"(${top_value:.2f}) comes from a single service, "
                            "which may indicate missed commitment discounts."),
                    evidence={"service": top_service,
                              "service_monthly_usd": round(top_value, 2),
                              "total_monthly_usd": round(total_cost, 2),
                              "share": round(share, 4)},
                    estimated_impact_usd=round(total_cost * 0.05, 2),
                    confidence=0.5,
                    risk="low",
                    priority="medium",
                    suggested_action=(f"Review commitment options (reserved capacity / "
                                      f"savings plans) for '{top_service}'.")))
        return created

    # ── Recording ──────────────────────────────────────────────────────

    def record_recommendation(self, tenant: str, category: str, title: str,
                              description: str, reason: str,
                              evidence: dict | None = None,
                              estimated_impact_usd: float = 0,
                              confidence: float = 0.5,
                              risk: str = "low",
                              priority: str = "medium",
                              suggested_action: str = "") -> dict:
        recommendation = {
            "recommendation_id": uuid4().hex,
            "tenant": tenant,
            "category": (category or "general").strip().lower(),
            "title": title,
            "description": description,
            "reason": reason,
            "evidence": dict(evidence or {}),
            "estimated_impact_usd": round(max(0.0, float(estimated_impact_usd)), 2),
            "confidence": round(min(1.0, max(0.0, float(confidence))), 4),
            "risk": risk if risk in RISK_LEVELS else "low",
            "priority": priority if priority in PRIORITY_LEVELS else "medium",
            "suggested_action": suggested_action,
            "status": STATUS_PENDING,
            "created_at": _utc_now(),
            "resolved_at": None,
        }
        self._recommendations[recommendation["recommendation_id"]] = recommendation
        return recommendation

    # ── Retrieval ──────────────────────────────────────────────────────

    def get_recommendations(self, tenant: str = "", category: str = "",
                            status: str = STATUS_PENDING,
                            limit: int = 50) -> list[dict]:
        selected = [
            record for record in reversed(list(self._recommendations.values()))
            if (not tenant or record["tenant"] == tenant)
            and (not category or record["category"] == category.strip().lower())
            and (not status or record["status"] == status)
        ]
        return selected[:max(0, limit)]

    def dismiss_recommendation(self, recommendation_id: str) -> dict | None:
        return self._set_status(recommendation_id, STATUS_DISMISSED)

    def accept_recommendation(self, recommendation_id: str) -> dict | None:
        return self._set_status(recommendation_id, STATUS_ACCEPTED)

    def _set_status(self, recommendation_id: str, status: str) -> dict | None:
        record = self._recommendations.get(recommendation_id)
        if record is None:
            return None
        record["status"] = status
        record["resolved_at"] = _utc_now()
        return record

    # ── Summary ────────────────────────────────────────────────────────

    def get_recommendation_summary(self, tenant: str = "") -> dict:
        records = [record for record in self._recommendations.values()
                   if not tenant or record["tenant"] == tenant]
        by_category: dict[str, int] = {}
        by_priority: dict[str, int] = {}
        by_status: dict[str, int] = {}
        total_impact = 0.0
        for record in records:
            by_category[record["category"]] = by_category.get(record["category"], 0) + 1
            by_priority[record["priority"]] = by_priority.get(record["priority"], 0) + 1
            by_status[record["status"]] = by_status.get(record["status"], 0) + 1
            total_impact += record["estimated_impact_usd"]
        return {
            "total": len(records),
            "by_category": by_category,
            "by_priority": by_priority,
            "by_status": by_status,
            "total_estimated_impact_usd": round(total_impact, 2),
        }


recommendation_service = RecommendationService()
