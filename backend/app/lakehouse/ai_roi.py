"""AI ROI Service - quantifies AI investment returns against honest baselines."""
from typing import Optional


class AIROIService:
    """Compares AI spend against baseline (human/legacy) costs to derive ROI."""

    def __init__(self):
        self.reports: list[dict] = []

    def evaluate(self, organization_id: str, ai_cost_usd: float,
                 baseline_cost_usd: float = 0.0, time_baseline_h: float = 0.0,
                 time_actual_h: float = 0.0,
                 quality_delta_positive: Optional[bool] = None) -> dict:
        """ai_cost_usd: total AI spend; baseline_cost_usd: honest non-AI cost
        (0 => ROI not measurable)."""
        hours_saved = max(0.0, time_baseline_h - time_actual_h) if time_baseline_h else 0.0
        measurable = baseline_cost_usd > 0
        net_value = baseline_cost_usd - ai_cost_usd if measurable else 0.0
        roi_multiple = net_value / max(ai_cost_usd, 1e-6) if measurable else 0.0

        report = {
            "organization_id": organization_id,
            "ai_cost_usd": round(ai_cost_usd, 2),
            "baseline_cost_usd": round(baseline_cost_usd, 2),
            "measurable": measurable,
            "net_value_usd": round(net_value, 2),
            "roi_multiple": round(roi_multiple, 2),
            "hours_saved": round(hours_saved, 2),
            "quality": {"measurable": quality_delta_positive is not None,
                        "quality_delta_positive": quality_delta_positive},
            "caveats": [] if measurable else ["no honest baseline provided; ROI not comparable"],
        }
        self.reports.append(report)
        return report

    def portfolio_summary(self) -> dict:
        if not self.reports:
            return {"reports": 0}
        total_ai = sum(r["ai_cost_usd"] for r in self.reports)
        total_baseline = sum(r["baseline_cost_usd"] for r in self.reports)
        return {"reports": len(self.reports),
                "total_ai_spend_usd": round(total_ai, 2),
                "total_baseline_usd": round(total_baseline, 2),
                "portfolio_roi_multiple":
                    round(total_baseline / max(total_ai, 1e-6), 2) if total_baseline else 0.0}