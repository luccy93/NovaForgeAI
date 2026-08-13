"""Agent Analytics Service - agent runs, success rates, costs and collaboration metrics."""
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class AgentRun:
    agent: str
    organization_id: str
    success: bool = True
    duration_s: float = 0.0
    cost_usd: float = 0.0
    steps: int = 1
    at: str = ""


class AgentAnalytics:
    """Aggregates autonomous agent run performance per agent and organization."""

    def __init__(self):
        self.runs: list[AgentRun] = []

    def record(self, run: AgentRun) -> AgentRun:
        if not run.at:
            run.at = datetime.now(timezone.utc).isoformat()
        self.runs.append(run)
        return run

    def overview(self, organization_id: Optional[str] = None) -> dict:
        rows = self._filter(organization_id)
        if not rows:
            return {"runs": 0}
        return {
            "runs": len(rows),
            "success_rate": round(sum(1 for r in rows if r.success) / len(rows), 4),
            "total_cost_usd": round(sum(r.cost_usd for r in rows), 4),
            "avg_duration_s": round(statistics.mean(r.duration_s for r in rows), 2),
            "avg_steps": round(statistics.mean(r.steps for r in rows), 2),
            "agents_active": len({r.agent for r in rows}),
        }

    def by_agent(self, organization_id: Optional[str] = None) -> list[dict]:
        rows = self._filter(organization_id)
        grouped: dict[str, dict] = {}
        for r in rows:
            entry = grouped.setdefault(r.agent, {"runs": 0, "successes": 0,
                                                 "cost_usd": 0.0, "durations": []})
            entry["runs"] += 1
            entry["successes"] += int(r.success)
            entry["cost_usd"] += r.cost_usd
            entry["durations"].append(r.duration_s)
        return [{"agent": agent, "runs": v["runs"],
                 "success_rate": round(v["successes"] / v["runs"], 4),
                 "total_cost_usd": round(v["cost_usd"], 4),
                 "avg_duration_s": round(statistics.mean(v["durations"]), 2)}
                for agent, v in sorted(grouped.items())]

    def failures(self, organization_id: Optional[str] = None, limit: int = 20) -> list[dict]:
        rows = [r for r in self._filter(organization_id) if not r.success]
        return [{"agent": r.agent, "duration_s": r.duration_s, "at": r.at}
                for r in rows[-limit:]]

    def _filter(self, organization_id: Optional[str] = None) -> list[AgentRun]:
        return [r for r in self.runs
                if not organization_id or r.organization_id == organization_id]


def compute_roi(cost_incurred: float, value_delivered: float) -> dict:
    guard = max(cost_incurred, 1e-6)
    return {"roi_multiple": round(value_delivered / guard, 2),
            "net_value_usd": round(value_delivered - cost_incurred, 2)}