"""RAG Analytics Service - retrieval quality, generation metrics and pipeline health."""
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class RAGQuery:
    organization_id: str
    query: str
    retrieved: int = 0
    relevant: int = 0
    latency_ms: float = 0.0
    tokens_out: int = 0
    grounded: bool = True
    success: bool = True
    at: str = ""


class RAGAnalytics:
    """Measures retrieval precision, coverage, latency and cost per query."""

    def __init__(self):
        self.queries: list[RAGQuery] = []

    def record(self, query: RAGQuery) -> RAGQuery:
        query.at = query.at or datetime.now(timezone.utc).isoformat()
        self.queries.append(query)
        return query

    def metrics(self, organization_id: Optional[str] = None) -> dict:
        rows = self._filter(organization_id)
        if not rows:
            return {"queries": 0}
        precision = [r.relevant / max(1, r.retrieved) for r in rows]
        latencies = [r.latency_ms for r in rows]
        return {
            "queries": len(rows),
            "avg_retrieved": round(statistics.mean(r.retrieved for r in rows), 2),
            "avg_precision": round(statistics.mean(precision), 4),
            "succeeded": round(sum(1 for r in rows if r.success) / len(rows), 4),
            "avg_latency_ms": round(statistics.mean(latencies), 2),
            "p95_latency_ms": round(self._p95(latencies), 2),
            "total_tokens_out": sum(r.tokens_out for r in rows),
        }

    def top_queries(self, organization_id: Optional[str] = None, limit: int = 10) -> list[dict]:
        rows = self._filter(organization_id)
        ranked = sorted(rows, key=lambda r: r.latency_ms, reverse=True)
        return [{"query": r.query, "retrieved": r.retrieved, "latency_ms": r.latency_ms,
                 "at": r.at} for r in ranked[:limit]]

    def pipeline_health(self, organization_id: Optional[str] = None) -> dict:
        rows = self._filter(organization_id)
        failures = [r for r in rows if not r.success]
        return {"runs": len(rows), "failures": len(failures),
                "failure_rate": round(len(failures) / max(1, len(rows)), 4)}

    def _filter(self, organization_id: Optional[str] = None) -> list[RAGQuery]:
        return [r for r in self.queries
                if not organization_id or r.organization_id == organization_id]

    @staticmethod
    def _p95(values: list[float]) -> float:
        if not values:
            return 0.0
        s = sorted(values)
        return s[min(len(s) - 1, int(0.95 * len(s)))]