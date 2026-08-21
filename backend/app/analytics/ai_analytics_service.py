"""Unified Analytics Platform -- AI Operations Analytics (Volume 50).

In-memory analytics for LLM calls, RAG queries, and agent runs:
usage, cost, latency, quality, and runaway-agent detection.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone


def _utcnow() -> datetime:
    return datetime.utcnow()


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def _parse_ts(value) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _in_window(dt: datetime | None, start: datetime | None, end: datetime | None) -> bool:
    if dt is None:
        return True
    if start is not None and dt < start:
        return False
    if end is not None and dt > end:
        return False
    return True


def _mean(values) -> float:
    return sum(values) / len(values) if values else 0.0


def _percentile(values, pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (len(ordered) - 1) * (pct / 100.0)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    frac = rank - low
    return float(ordered[low] + (ordered[high] - ordered[low]) * frac)


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


class AIAnalyticsService:
    """In-memory AI operations analytics store."""

    def __init__(self) -> None:
        self._ai_calls: list[dict] = []
        self._rag_queries: list[dict] = []
        self._agent_runs: list[dict] = []

    # ── Recording ─────────────────────────────────────────────────────

    def record_ai_call(self, tenant: str, model: str, provider: str,
                       input_tokens: int = 0, output_tokens: int = 0,
                       cached_tokens: int = 0, latency_ms: float = 0,
                       success: bool = True, cost_usd: float = 0,
                       agent: str = "", workflow: str = "",
                       error_message: str = "") -> dict:
        ts = _utcnow()
        record = {
            "id": uuid.uuid4().hex,
            "tenant": tenant,
            "model": model,
            "provider": provider,
            "input_tokens": int(input_tokens or 0),
            "output_tokens": int(output_tokens or 0),
            "cached_tokens": int(cached_tokens or 0),
            "total_tokens": int(input_tokens or 0) + int(output_tokens or 0),
            "latency_ms": float(latency_ms or 0),
            "success": bool(success),
            "cost_usd": float(cost_usd or 0),
            "agent": agent,
            "workflow": workflow,
            "error_message": error_message if not success else "",
            "created_at": _iso(ts),
            "_dt": ts,
        }
        self._ai_calls.append(record)
        return {k: v for k, v in record.items() if k != "_dt"}

    def record_rag_query(self, tenant: str, query: str = "", results_count: int = 0,
                         context_size: int = 0, latency_ms: float = 0,
                         success: bool = True) -> dict:
        ts = _utcnow()
        record = {
            "id": uuid.uuid4().hex,
            "tenant": tenant,
            "query": query,
            "query_fingerprint": hashlib.sha256(f"{tenant}|{query}".encode("utf-8")).hexdigest()[:16],
            "results_count": int(results_count or 0),
            "context_size": int(context_size or 0),
            "latency_ms": float(latency_ms or 0),
            "success": bool(success),
            "created_at": _iso(ts),
            "_dt": ts,
        }
        self._rag_queries.append(record)
        return {k: v for k, v in record.items() if k != "_dt"}

    def record_agent_run(self, tenant: str, agent_name: str, task: str = "",
                         success: bool = True, tool_calls: int = 0,
                         iterations: int = 0, tokens: int = 0,
                         cost_usd: float = 0, duration_ms: float = 0,
                         human_approved: bool = False) -> dict:
        ts = _utcnow()
        record = {
            "id": uuid.uuid4().hex,
            "tenant": tenant,
            "agent_name": agent_name,
            "task": task,
            "success": bool(success),
            "tool_calls": int(tool_calls or 0),
            "iterations": int(iterations or 0),
            "tokens": int(tokens or 0),
            "cost_usd": float(cost_usd or 0),
            "duration_ms": float(duration_ms or 0),
            "human_approved": bool(human_approved),
            "created_at": _iso(ts),
            "_dt": ts,
        }
        self._agent_runs.append(record)
        return {k: v for k, v in record.items() if k != "_dt"}

    # ── Filtering helpers ─────────────────────────────────────────────

    def _window_calls(self, tenant: str, start_time: str = "", end_time: str = "") -> list[dict]:
        start_dt, end_dt = _parse_ts(start_time), _parse_ts(end_time)
        return [
            c for c in self._ai_calls
            if c["tenant"] == tenant and _in_window(c["_dt"], start_dt, end_dt)
        ]

    def _window_rag(self, tenant: str, start_time: str = "", end_time: str = "") -> list[dict]:
        start_dt, end_dt = _parse_ts(start_time), _parse_ts(end_time)
        return [
            q for q in self._rag_queries
            if q["tenant"] == tenant and _in_window(q["_dt"], start_dt, end_dt)
        ]

    def _window_runs(self, tenant: str, start_time: str = "", end_time: str = "") -> list[dict]:
        start_dt, end_dt = _parse_ts(start_time), _parse_ts(end_time)
        return [
            r for r in self._agent_runs
            if r["tenant"] == tenant and _in_window(r["_dt"], start_dt, end_dt)
        ]

    # ── Model comparison & usage ──────────────────────────────────────

    def get_model_comparison(self, tenant: str, models: list[str] = None,
                             start_time: str = "", end_time: str = "") -> list[dict]:
        wanted = set(models or [])
        calls = [
            c for c in self._window_calls(tenant, start_time, end_time)
            if not wanted or c["model"] in wanted
        ]
        grouped: dict[str, list[dict]] = {}
        for call in calls:
            grouped.setdefault(call["model"], []).append(call)

        comparison: list[dict] = []
        for model, rows in grouped.items():
            succeeded = sum(1 for r in rows if r["success"])
            providers = sorted({r["provider"] for r in rows} - {""})
            total_cost = sum(r["cost_usd"] for r in rows)
            total_tokens = sum(r["total_tokens"] for r in rows)
            latencies = [r["latency_ms"] for r in rows]
            comparison.append({
                "model": model,
                "providers": providers,
                "calls": len(rows),
                "success_rate": _rate(succeeded, len(rows)),
                "error_rate": round(1 - _rate(succeeded, len(rows)), 4) if rows else 0.0,
                "avg_latency_ms": round(_mean(latencies), 4),
                "p95_latency_ms": round(_percentile(latencies, 95), 4),
                "total_tokens": total_tokens,
                "avg_tokens_per_call": round(_mean([r["total_tokens"] for r in rows]), 4),
                "cached_tokens": sum(r["cached_tokens"] for r in rows),
                "total_cost_usd": round(total_cost, 6),
                "avg_cost_per_call_usd": round(total_cost / len(rows), 6) if rows else 0.0,
                "cost_per_1k_tokens_usd": round(total_cost * 1000 / total_tokens, 6) if total_tokens else 0.0,
            })
        comparison.sort(key=lambda row: row["total_cost_usd"], reverse=True)
        return comparison

    def get_ai_usage_summary(self, tenant: str, start_time: str = "",
                             end_time: str = "") -> dict:
        calls = self._window_calls(tenant, start_time, end_time)
        succeeded = sum(1 for c in calls if c["success"])
        total_input = sum(c["input_tokens"] for c in calls)
        total_output = sum(c["output_tokens"] for c in calls)
        total_cached = sum(c["cached_tokens"] for c in calls)
        total_cost = sum(c["cost_usd"] for c in calls)
        rag = self._window_rag(tenant, start_time, end_time)
        runs = self._window_runs(tenant, start_time, end_time)
        return {
            "total_calls": len(calls),
            "successful_calls": succeeded,
            "failed_calls": len(calls) - succeeded,
            "success_rate": _rate(succeeded, len(calls)),
            "input_tokens": total_input,
            "output_tokens": total_output,
            "cached_tokens": total_cached,
            "total_tokens": total_input + total_output,
            "cache_hit_rate": _rate(total_cached, total_input + total_output),
            "total_cost_usd": round(total_cost, 6),
            "avg_cost_per_call_usd": round(total_cost / len(calls), 6) if calls else 0.0,
            "avg_latency_ms": round(_mean([c["latency_ms"] for c in calls]), 4),
            "distinct_models": len({c["model"] for c in calls}),
            "distinct_providers": len({c["provider"] for c in calls}),
            "rag_queries": len(rag),
            "agent_runs": len(runs),
        }

    # ── Agents ────────────────────────────────────────────────────────

    def get_agent_analytics(self, tenant: str, start_time: str = "",
                            end_time: str = "") -> dict:
        runs = self._window_runs(tenant, start_time, end_time)
        succeeded = sum(1 for r in runs if r["success"])
        approved = sum(1 for r in runs if r["human_approved"])
        by_agent: dict[str, dict] = {}
        for run in runs:
            stats = by_agent.setdefault(run["agent_name"], {
                "runs": 0, "successes": 0, "tool_calls": 0,
                "tokens": 0, "cost_usd": 0.0, "duration_ms": 0.0,
            })
            stats["runs"] += 1
            stats["successes"] += 1 if run["success"] else 0
            stats["tool_calls"] += run["tool_calls"]
            stats["tokens"] += run["tokens"]
            stats["cost_usd"] += run["cost_usd"]
            stats["duration_ms"] += run["duration_ms"]
        for name, stats in by_agent.items():
            stats["success_rate"] = _rate(stats["successes"], stats["runs"])
            stats["cost_usd"] = round(stats["cost_usd"], 6)
            stats["avg_duration_ms"] = round(stats["duration_ms"] / stats["runs"], 4)
        return {
            "total_runs": len(runs),
            "successful_runs": succeeded,
            "failed_runs": len(runs) - succeeded,
            "success_rate": _rate(succeeded, len(runs)),
            "total_tool_calls": sum(r["tool_calls"] for r in runs),
            "avg_tool_calls": round(_mean([r["tool_calls"] for r in runs]), 4),
            "total_iterations": sum(r["iterations"] for r in runs),
            "avg_iterations": round(_mean([r["iterations"] for r in runs]), 4),
            "max_iterations": max((r["iterations"] for r in runs), default=0),
            "total_tokens": sum(r["tokens"] for r in runs),
            "total_cost_usd": round(sum(r["cost_usd"] for r in runs), 6),
            "avg_duration_ms": round(_mean([r["duration_ms"] for r in runs]), 4),
            "human_approval_rate": _rate(approved, len(runs)),
            "distinct_agents": len(by_agent),
            "by_agent": by_agent,
        }

    # ── RAG ───────────────────────────────────────────────────────────

    def get_rag_analytics(self, tenant: str, start_time: str = "",
                          end_time: str = "") -> dict:
        queries = self._window_rag(tenant, start_time, end_time)
        succeeded = sum(1 for q in queries if q["success"])
        zero_results = sum(1 for q in queries if q["results_count"] == 0)
        latencies = [q["latency_ms"] for q in queries]
        return {
            "total_queries": len(queries),
            "successful_queries": succeeded,
            "failed_queries": len(queries) - succeeded,
            "success_rate": _rate(succeeded, len(queries)),
            "avg_latency_ms": round(_mean(latencies), 4),
            "p95_latency_ms": round(_percentile(latencies, 95), 4),
            "avg_results_count": round(_mean([q["results_count"] for q in queries]), 4),
            "avg_context_size": round(_mean([q["context_size"] for q in queries]), 4),
            "zero_result_queries": zero_results,
            "zero_result_rate": _rate(zero_results, len(queries)),
        }

    # ── Cost ──────────────────────────────────────────────────────────

    def get_model_cost_report(self, tenant: str, start_time: str = "",
                              end_time: str = "") -> dict:
        calls = self._window_calls(tenant, start_time, end_time)
        total_cost = sum(c["cost_usd"] for c in calls)
        grouped: dict[str, list[dict]] = {}
        for call in calls:
            grouped.setdefault(call["model"], []).append(call)

        models: list[dict] = []
        for model, rows in grouped.items():
            cost = sum(r["cost_usd"] for r in rows)
            input_tokens = sum(r["input_tokens"] for r in rows)
            output_tokens = sum(r["output_tokens"] for r in rows)
            cached_tokens = sum(r["cached_tokens"] for r in rows)
            models.append({
                "model": model,
                "calls": len(rows),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cached_tokens": cached_tokens,
                "total_tokens": input_tokens + output_tokens,
                "cost_usd": round(cost, 6),
                "cost_share_pct": round(cost * 100.0 / total_cost, 2) if total_cost else 0.0,
                "avg_cost_per_call_usd": round(cost / len(rows), 6) if rows else 0.0,
            })
        models.sort(key=lambda row: row["cost_usd"], reverse=True)
        return {
            "total_cost_usd": round(total_cost, 6),
            "total_calls": len(calls),
            "models": models,
        }

    # ── Runaway detection ─────────────────────────────────────────────

    def detect_runaway_agent(self, tenant: str, threshold_cost: float = 10.0,
                             threshold_iterations: int = 50) -> list[dict]:
        runs = [r for r in self._agent_runs if r["tenant"] == tenant]
        grouped: dict[str, list[dict]] = {}
        for run in runs:
            grouped.setdefault(run["agent_name"], []).append(run)

        flagged: list[dict] = []
        for agent_name, rows in grouped.items():
            total_cost = sum(r["cost_usd"] for r in rows)
            max_iterations = max((r["iterations"] for r in rows), default=0)
            reasons: list[str] = []
            if total_cost > threshold_cost:
                reasons.append("cost_threshold_exceeded")
            if max_iterations > threshold_iterations:
                reasons.append("iteration_threshold_exceeded")
            if not reasons:
                continue
            flagged.append({
                "tenant": tenant,
                "agent_name": agent_name,
                "runs": len(rows),
                "total_cost_usd": round(total_cost, 6),
                "max_iterations": max_iterations,
                "total_tokens": sum(r["tokens"] for r in rows),
                "total_tool_calls": sum(r["tool_calls"] for r in rows),
                "reasons": reasons,
                "threshold_cost": threshold_cost,
                "threshold_iterations": threshold_iterations,
            })
        flagged.sort(key=lambda item: item["total_cost_usd"], reverse=True)
        return flagged


ai_analytics_service = AIAnalyticsService()
