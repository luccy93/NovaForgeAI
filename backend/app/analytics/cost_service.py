"""Unified Analytics Platform -- Cost Attribution Service (Volume 50).

In-memory cost ledger for NovaForge. Records real cost entries attributed
to tenants, organizations, projects, models, providers, agents, workflows
and users. This service never fabricates cost data: every record originates
from an explicit ``record_cost`` call, and estimated entries are flagged via
``is_estimated`` / ``cost_basis`` so they can never be mistaken for actuals.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

COST_TYPE_TOTAL = "total"

DIMENSION_COST_TYPE = "cost_type"
DIMENSIONS = (
    DIMENSION_COST_TYPE,
    "organization",
    "workspace",
    "project",
    "repository",
    "environment",
    "model",
    "provider",
    "agent",
    "workflow",
    "user_id",
)

GRANULARITY_HOUR = "hour"
GRANULARITY_DAY = "day"
GRANULARITY_WEEK = "week"
GRANULARITY_MONTH = "month"
GRANULARITIES = (GRANULARITY_HOUR, GRANULARITY_DAY, GRANULARITY_WEEK, GRANULARITY_MONTH)

BASIS_ACTUAL = "actual"
BASIS_ESTIMATED = "estimated"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _in_range(timestamp: datetime, start: datetime | None, end: datetime | None) -> bool:
    if start is not None and timestamp < start:
        return False
    if end is not None and timestamp > end:
        return False
    return True


def _bucket_key(timestamp: datetime, granularity: str) -> str:
    moment = timestamp.astimezone(timezone.utc)
    if granularity == GRANULARITY_HOUR:
        return moment.replace(minute=0, second=0, microsecond=0).isoformat()
    if granularity == GRANULARITY_DAY:
        return moment.date().isoformat()
    if granularity == GRANULARITY_WEEK:
        monday = moment.date() - timedelta(days=moment.weekday())
        return monday.isoformat()
    if granularity == GRANULARITY_MONTH:
        return moment.strftime("%Y-%m")
    raise ValueError(f"unsupported granularity: {granularity!r}")


def _group_entries(entries: list[dict], field: str) -> list[dict]:
    groups: dict[str, dict] = {}
    for entry in entries:
        value = str(entry.get(field) or "") if field != DIMENSION_COST_TYPE else str(entry.get("cost_type") or "")
        if not value:
            continue
        bucket = groups.setdefault(value, {"value": value, "total_usd": 0.0, "count": 0, "estimated_usd": 0.0})
        amount = float(entry.get("amount_usd") or 0.0)
        bucket["total_usd"] += amount
        bucket["count"] += 1
        if entry.get("is_estimated"):
            bucket["estimated_usd"] += amount
    grouped = [
        {
            "value": value,
            "total_usd": round(stats["total_usd"], 6),
            "count": stats["count"],
            "estimated_usd": round(stats["estimated_usd"], 6),
        }
        for value, stats in groups.items()
    ]
    grouped.sort(key=lambda item: item["total_usd"], reverse=True)
    return grouped


class CostService:
    """In-memory cost attribution ledger."""

    def __init__(self) -> None:
        self._costs: list[dict] = []

    def record_cost(
        self,
        tenant: str,
        cost_type: str,
        amount_usd: float,
        period_start: str,
        period_end: str,
        organization: str = "",
        workspace: str = "",
        project: str = "",
        repository: str = "",
        environment: str = "",
        model: str = "",
        provider: str = "",
        agent: str = "",
        workflow: str = "",
        user_id: str = "",
        is_estimated: bool = False,
        metadata: dict = None,
    ) -> dict:
        if not tenant:
            raise ValueError("tenant is required")
        if not cost_type:
            raise ValueError("cost_type is required")
        if not isinstance(amount_usd, (int, float)) or isinstance(amount_usd, bool):
            raise ValueError("amount_usd must be a number")
        if amount_usd != amount_usd or amount_usd in (float("inf"), float("-inf")):
            raise ValueError("amount_usd must be finite")
        if amount_usd < 0:
            raise ValueError("amount_usd must be non-negative")
        now = _utcnow()
        safe_metadata = json.loads(json.dumps(metadata or {}, default=str))
        entry = {
            "id": f"cost_{uuid.uuid4().hex}",
            "tenant": tenant,
            "cost_type": cost_type,
            "amount_usd": round(float(amount_usd), 6),
            "currency": "USD",
            "period_start": period_start,
            "period_end": period_end,
            "organization": organization,
            "workspace": workspace,
            "project": project,
            "repository": repository,
            "environment": environment,
            "model": model,
            "provider": provider,
            "agent": agent,
            "workflow": workflow,
            "user_id": user_id,
            "is_estimated": bool(is_estimated),
            "cost_basis": BASIS_ESTIMATED if is_estimated else BASIS_ACTUAL,
            "metadata": safe_metadata,
            "timestamp": now.isoformat(),
            "recorded_at": now.isoformat(),
        }
        self._costs.append(entry)
        return self._copy(entry)

    def get_costs(
        self,
        tenant: str,
        cost_type: str = "",
        organization: str = "",
        project: str = "",
        model: str = "",
        provider: str = "",
        start_time: str = "",
        end_time: str = "",
        limit: int = 1000,
    ) -> list[dict]:
        start = _parse_time(start_time)
        end = _parse_time(end_time)
        results: list[dict] = []
        for entry in self._costs:
            if entry.get("tenant") != tenant:
                continue
            if cost_type and entry.get("cost_type") != cost_type:
                continue
            if organization and entry.get("organization") != organization:
                continue
            if project and entry.get("project") != project:
                continue
            if model and entry.get("model") != model:
                continue
            if provider and entry.get("provider") != provider:
                continue
            timestamp = _parse_time(entry.get("timestamp"))
            if timestamp is None or not _in_range(timestamp, start, end):
                continue
            results.append(self._copy(entry))
            if limit is not None and limit >= 0 and len(results) >= limit:
                break
        return results

    def get_cost_summary(
        self,
        tenant: str,
        group_by: str = "cost_type",
        start_time: str = "",
        end_time: str = "",
    ) -> dict:
        if group_by not in DIMENSIONS:
            raise ValueError(f"unsupported group_by dimension: {group_by!r}")
        start = _parse_time(start_time)
        end = _parse_time(end_time)
        entries = self._filtered(tenant, start, end)
        total = sum(float(entry.get("amount_usd") or 0.0) for entry in entries)
        estimated = sum(
            float(entry.get("amount_usd") or 0.0) for entry in entries if entry.get("is_estimated")
        )
        return {
            "tenant": tenant,
            "group_by": group_by,
            "start_time": start_time,
            "end_time": end_time,
            "total_usd": round(total, 6),
            "entry_count": len(entries),
            "estimated_usd": round(estimated, 6),
            "actual_usd": round(total - estimated, 6),
            "groups": _group_entries(entries, group_by),
            "generated_at": _utcnow().isoformat(),
        }

    def get_total_cost(
        self,
        tenant: str,
        cost_type: str = "total",
        start_time: str = "",
        end_time: str = "",
    ) -> float:
        start = _parse_time(start_time)
        end = _parse_time(end_time)
        entries = self._filtered(tenant, start, end)
        if cost_type and cost_type != COST_TYPE_TOTAL:
            entries = [entry for entry in entries if entry.get("cost_type") == cost_type]
        total = sum(float(entry.get("amount_usd") or 0.0) for entry in entries)
        return round(total, 6)

    def get_ai_cost_breakdown(
        self,
        tenant: str,
        start_time: str = "",
        end_time: str = "",
    ) -> dict:
        start = _parse_time(start_time)
        end = _parse_time(end_time)
        ai_entries = [
            entry
            for entry in self._filtered(tenant, start, end)
            if entry.get("cost_type") == "model" or entry.get("model") or entry.get("provider") or entry.get("agent")
        ]
        total = sum(float(entry.get("amount_usd") or 0.0) for entry in ai_entries)
        estimated = sum(
            float(entry.get("amount_usd") or 0.0) for entry in ai_entries if entry.get("is_estimated")
        )
        return {
            "tenant": tenant,
            "start_time": start_time,
            "end_time": end_time,
            "total_ai_cost_usd": round(total, 6),
            "actual_usd": round(total - estimated, 6),
            "estimated_usd": round(estimated, 6),
            "entry_count": len(ai_entries),
            "by_model": _group_entries(ai_entries, "model"),
            "by_provider": _group_entries(ai_entries, "provider"),
            "by_agent": _group_entries(ai_entries, "agent"),
            "generated_at": _utcnow().isoformat(),
        }

    def get_cost_trend(
        self,
        tenant: str,
        granularity: str = "day",
        start_time: str = "",
        end_time: str = "",
    ) -> list[dict]:
        if granularity not in GRANULARITIES:
            raise ValueError(f"unsupported granularity: {granularity!r}")
        start = _parse_time(start_time)
        end = _parse_time(end_time)
        buckets: dict[str, dict] = {}
        for entry in self._filtered(tenant, start, end):
            timestamp = _parse_time(entry.get("timestamp"))
            if timestamp is None:
                continue
            key = _bucket_key(timestamp, granularity)
            bucket = buckets.setdefault(
                key,
                {"period": key, "granularity": granularity, "total_usd": 0.0, "entry_count": 0, "estimated_usd": 0.0},
            )
            amount = float(entry.get("amount_usd") or 0.0)
            bucket["total_usd"] += amount
            bucket["entry_count"] += 1
            if entry.get("is_estimated"):
                bucket["estimated_usd"] += amount
        trend = [
            {
                "period": stats["period"],
                "granularity": granularity,
                "total_usd": round(stats["total_usd"], 6),
                "entry_count": stats["entry_count"],
                "estimated_usd": round(stats["estimated_usd"], 6),
            }
            for _, stats in sorted(buckets.items())
        ]
        return trend

    def compare_models(
        self,
        tenant: str,
        models: list[str] = None,
        start_time: str = "",
        end_time: str = "",
    ) -> list[dict]:
        start = _parse_time(start_time)
        end = _parse_time(end_time)
        selected = set(models or [])
        per_model: dict[str, list[dict]] = {}
        for entry in self._filtered(tenant, start, end):
            model = str(entry.get("model") or "")
            if not model:
                continue
            if selected and model not in selected:
                continue
            per_model.setdefault(model, []).append(entry)
        comparisons: list[dict] = []
        for model, entries in per_model.items():
            latencies = []
            successes = []
            total = 0.0
            estimated = 0.0
            for entry in entries:
                amount = float(entry.get("amount_usd") or 0.0)
                total += amount
                if entry.get("is_estimated"):
                    estimated += amount
                entry_metadata = entry.get("metadata") or {}
                latency = entry_metadata.get("latency_ms")
                if isinstance(latency, (int, float)) and not isinstance(latency, bool):
                    latencies.append(float(latency))
                success = entry_metadata.get("success")
                if isinstance(success, bool):
                    successes.append(success)
            comparisons.append(
                {
                    "model": model,
                    "call_count": len(entries),
                    "total_cost_usd": round(total, 6),
                    "avg_cost_per_call_usd": round(total / len(entries), 6) if entries else 0.0,
                    "actual_usd": round(total - estimated, 6),
                    "estimated_usd": round(estimated, 6),
                    "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else None,
                    "latency_sample_size": len(latencies),
                    "success_rate_percent": round(sum(successes) / len(successes) * 100.0, 2) if successes else None,
                    "success_sample_size": len(successes),
                }
            )
        comparisons.sort(key=lambda item: item["total_cost_usd"], reverse=True)
        return comparisons

    def get_cost_by_dimension(
        self,
        tenant: str,
        dimension: str = "project",
        start_time: str = "",
        end_time: str = "",
    ) -> list[dict]:
        if dimension not in DIMENSIONS:
            raise ValueError(f"unsupported dimension: {dimension!r}")
        start = _parse_time(start_time)
        end = _parse_time(end_time)
        entries = self._filtered(tenant, start, end)
        return _group_entries(entries, dimension)

    def to_json(self, tenant: str = "", limit: int = None) -> str:
        entries = self._costs
        if tenant:
            entries = [entry for entry in entries if entry.get("tenant") == tenant]
        if limit is not None and limit >= 0:
            entries = entries[:limit]
        return json.dumps([self._copy(entry) for entry in entries], indent=2, default=str)

    def _filtered(self, tenant: str, start: datetime | None, end: datetime | None) -> list[dict]:
        matched = []
        for entry in self._costs:
            if entry.get("tenant") != tenant:
                continue
            timestamp = _parse_time(entry.get("timestamp"))
            if timestamp is None or not _in_range(timestamp, start, end):
                continue
            matched.append(entry)
        return matched

    @staticmethod
    def _copy(entry: dict) -> dict:
        copied = dict(entry)
        copied["metadata"] = dict(entry.get("metadata") or {})
        return copied


cost_service = CostService()
