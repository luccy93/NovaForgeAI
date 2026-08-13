"""FinOps Analytics - cloud spend, savings, commitment coverage and unit cost trends."""
import statistics
from typing import Optional


class FinOpsAnalytics:
    """Cloud cost allocation and optimization metrics per organization."""

    def __init__(self):
        self.spend_series: list[dict] = []  # {"at", "provider", "service", "amount_usd", "org"}
        self.waivers: list[dict] = []        # {"at", "org", "type", "savings_usd"}

    def record_spend(self, org: str, provider: str, service: str,
                     amount_usd: float, at: str) -> None:
        self.spend_series.append({"at": at, "provider": provider,
                                  "service": service, "amount_usd": amount_usd, "org": org})

    def record_savings(self, org: str, kind: str, savings_usd: float, at: str) -> None:
        self.waivers.append({"at": at, "org": org, "kind": kind, "savings_usd": savings_usd})

    def total_spend(self, org: Optional[str] = None) -> dict:
        rows = self._spend(org)
        total = sum(r["amount_usd"] for r in rows)
        by_provider = {}
        for r in rows:
            by_provider[r["provider"]] = round(by_provider.get(r["provider"], 0.0) + r["amount_usd"], 2)
        return {"total_spend_usd": round(total, 2),
                "by_provider": by_provider,
                "months": len({r["at"][:7] for r in rows})}

    def spend_trend(self, org: Optional[str] = None) -> dict:
        rows = self._spend(org)
        monthly = {}
        for r in rows:
            key = r["at"][:7]
            monthly[key] = monthly.get(key, 0.0) + r["amount_usd"]
        return {"monthly": {k: round(v, 2) for k, v in sorted(monthly.items())},
                "growth_pct": self._growth_trend([monthly[k] for k in sorted(monthly)])}

    def savings_recognized(self, org: Optional[str] = None) -> dict:
        rows = [r for r in self.waivers if not org or r["org"] == org]
        total = sum(r["savings_usd"] for r in rows)
        by_kind = {}
        for r in rows:
            by_kind[r["kind"]] = round(by_kind.get(r["kind"], 0.0) + r["savings_usd"], 2)
        return {"total_savings_usd": round(total, 2), "by_kind": by_kind,
                "initiatives": len(rows)}

    def idle_opportunity(self, resources: list[dict], threshold_hours: float = 24.0) -> dict:
        """resources: [{name, active_hours, cost_hourly}] -> estimates of idle waste."""
        idle = [r for r in resources if r.get("active_hours", 0.0) <= threshold_hours]
        wasted = sum(r.get("cost_hourly", 0.0) * (threshold_hours - r.get("active_hours", 0.0))
                     for r in idle)
        return {"idle_resources": len(idle), "total_resources": len(resources),
                "estimated_waste_usd": round(wasted, 2)}

    def unit_cost_trend(self, metric: str, series: list[tuple[str, float]]) -> dict:
        costs = [{"at": at, "unit_cost": value} for at, value in series]
        values = [c["unit_cost"] for c in costs]
        if len(values) < 2:
            return {"note": "need >=2 periods"}
        return {"metric": metric, "latest": round(values[-1], 4),
                "change_pct": round((values[-1] - values[0]) / max(1e-6, values[0]) * 100.0, 2),
                "mean": round(statistics.mean(values), 4)}

    def _spend(self, org: Optional[str] = None) -> list[dict]:
        return [r for r in self.spend_series if not org or r["org"] == org]

    @staticmethod
    def _growth_trend(values: list[float]) -> float:
        if len(values) < 2:
            return 0.0
        return round((values[-1] - values[0]) / max(1e-6, abs(values[0])) * 100.0, 2)


def roi(cost: float, benefit: float) -> dict:
    base = max(cost, 1e-6)
    return {"roi_multiple": round(benefit / base, 2),
            "net_usd": round(benefit - cost, 2)}