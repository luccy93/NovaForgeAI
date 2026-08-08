import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
import json, uuid, hashlib, time, math
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)


class TelemetryEvent(Enum):
    REQUEST = "request"
    RESPONSE = "response"
    FAILURE = "failure"
    RETRY = "retry"
    TIMEOUT = "timeout"
    STREAMING_START = "streaming_start"
    STREAMING_END = "streaming_end"
    TOOL_CALL = "tool_call"
    AGENT_CALL = "agent_call"
    MEMORY_USAGE = "memory_usage"
    EMBEDDING_USAGE = "embedding_usage"
    SEARCH = "search"
    RAG = "rag"
    RERANK = "rerank"
    CITATION = "citation"


class TelemetrySeverity(Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class TelemetryRecord:
    id: str = ""
    event: TelemetryEvent = TelemetryEvent.REQUEST
    model: str = ""
    provider: str = ""
    org_id: str = ""
    workspace_id: Optional[str] = None
    latency_ms: float = 0.0
    tokens_prompt: int = 0
    tokens_completion: int = 0
    cost: float = 0.0
    success: bool = True
    error: Optional[str] = None
    streaming: bool = False
    tool_calls: int = 0
    agent_calls: int = 0
    memory_mb: float = 0.0
    embedding_dimension: int = 0
    search_time_ms: float = 0.0
    rag_time_ms: float = 0.0
    context_tokens: int = 0
    rerank_time_ms: float = 0.0
    timestamp: str = ""
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["event"] = self.event.value
        return d

    @staticmethod
    def from_dict(data: dict) -> "TelemetryRecord":
        data = data.copy()
        data["event"] = TelemetryEvent(data.get("event", "request"))
        return TelemetryRecord(**data)


@dataclass
class TelemetryStats:
    period_start: str = ""
    period_end: str = ""
    total_requests: int = 0
    success_rate: float = 0.0
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    total_tokens: int = 0
    total_cost: float = 0.0
    failure_count: int = 0
    retry_count: int = 0
    timeout_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "TelemetryStats":
        return TelemetryStats(**data)


@dataclass
class ModelTelemetry:
    model: str = ""
    provider: str = ""
    requests: int = 0
    avg_latency: float = 0.0
    avg_tokens: int = 0
    error_rate: float = 0.0
    cost: float = 0.0
    last_used: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "ModelTelemetry":
        return ModelTelemetry(**data)


@dataclass
class DashboardDefinition:
    id: str = ""
    name: str = ""
    metrics: list[str] = field(default_factory=list)
    timeframe: str = "24h"
    config: dict = field(default_factory=dict)
    created_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "DashboardDefinition":
        return DashboardDefinition(**data)


class TelemetryCollector:
    def __init__(self, storage_dir: str):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._records_file = self.storage_dir / "telemetry_records.json"
        self._records: list[TelemetryRecord] = []
        self._telemetry = defaultdict(int)
        self._load()

    def _save(self):
        try:
            data = [r.to_dict() for r in self._records]
            self._records_file.write_text(json.dumps(data, indent=2, default=str))
        except Exception as e:
            logger.error("Failed to save telemetry records: %s", e, exc_info=True)
            raise

    def _load(self):
        try:
            if self._records_file.exists():
                data = json.loads(self._records_file.read_text())
                self._records = [TelemetryRecord.from_dict(r) for r in data]
        except Exception as e:
            logger.error("Failed to load telemetry records: %s", e, exc_info=True)

    def record_event(self, record: TelemetryRecord) -> TelemetryRecord:
        self._telemetry["events_recorded"] += 1
        self._records.append(record)
        self._save()
        logger.debug("Recorded telemetry event: %s (%s)", record.event.value, record.model or "N/A")
        return record

    def get_records(self, org_id: Optional[str] = None, limit: int = 500) -> list[TelemetryRecord]:
        self._telemetry["get_records_calls"] += 1
        if org_id:
            return [r for r in self._records if r.org_id == org_id][-limit:]
        return self._records[-limit:]

    def get_records_by_event(self, event: TelemetryEvent, org_id: Optional[str] = None, limit: int = 500) -> list[TelemetryRecord]:
        self._telemetry["get_records_by_event_calls"] += 1
        results = [r for r in self._records if r.event == event]
        if org_id:
            results = [r for r in results if r.org_id == org_id]
        return results[-limit:]

    def get_model_telemetry(self, model: str, org_id: Optional[str] = None) -> ModelTelemetry:
        self._telemetry["get_model_telemetry_calls"] += 1
        records = [r for r in self._records if r.model == model]
        if org_id:
            records = [r for r in records if r.org_id == org_id]
        if not records:
            return ModelTelemetry(model=model)
        latencies = [r.latency_ms for r in records if r.latency_ms > 0]
        total_tokens = sum(r.tokens_prompt + r.tokens_completion for r in records)
        errors = sum(1 for r in records if not r.success)
        return ModelTelemetry(
            model=model,
            provider=records[-1].provider if records else "",
            requests=len(records),
            avg_latency=round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
            avg_tokens=total_tokens // len(records) if records else 0,
            error_rate=round(errors / len(records) * 100.0, 2) if records else 0.0,
            cost=round(sum(r.cost for r in records), 6),
            last_used=records[-1].timestamp,
        )

    def get_provider_telemetry(self, provider: str, org_id: Optional[str] = None) -> dict:
        self._telemetry["get_provider_telemetry_calls"] += 1
        records = [r for r in self._records if r.provider == provider]
        if org_id:
            records = [r for r in records if r.org_id == org_id]
        if not records:
            return {"provider": provider, "requests": 0}
        latencies = [r.latency_ms for r in records if r.latency_ms > 0]
        errors = sum(1 for r in records if not r.success)
        models_used = set(r.model for r in records if r.model)
        return {
            "provider": provider,
            "requests": len(records),
            "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
            "total_cost": round(sum(r.cost for r in records), 6),
            "error_rate": round(errors / len(records) * 100.0, 2) if records else 0.0,
            "models_used": list(models_used),
            "last_request": records[-1].timestamp,
        }

    def get_failure_analytics(self, org_id: Optional[str] = None) -> dict:
        self._telemetry["get_failure_analytics_calls"] += 1
        failures = [r for r in self._records if not r.success]
        if org_id:
            failures = [r for r in failures if r.org_id == org_id]
        by_event = defaultdict(int)
        by_model = defaultdict(int)
        by_provider = defaultdict(int)
        by_error = defaultdict(int)
        for r in failures:
            by_event[r.event.value] += 1
            by_model[r.model] += 1
            by_provider[r.provider] += 1
            if r.error:
                by_error[r.error[:100]] += 1
        return {
            "total_failures": len(failures),
            "by_event": dict(by_event),
            "by_model": dict(by_model),
            "by_provider": dict(by_provider),
            "top_errors": dict(sorted(by_error.items(), key=lambda x: x[1], reverse=True)[:10]),
        }

    def get_latency_distribution(self, org_id: Optional[str] = None) -> dict:
        self._telemetry["get_latency_distribution_calls"] += 1
        records = self._records
        if org_id:
            records = [r for r in records if r.org_id == org_id]
        latencies = sorted(r.latency_ms for r in records if r.latency_ms > 0)
        if not latencies:
            return {"min": 0.0, "max": 0.0, "avg": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0}
        n = len(latencies)
        def percentile(p):
            idx = int(math.ceil(p / 100.0 * n)) - 1
            return latencies[max(0, min(idx, n - 1))]
        return {
            "min": round(latencies[0], 2),
            "max": round(latencies[-1], 2),
            "avg": round(sum(latencies) / n, 2),
            "p50": round(percentile(50), 2),
            "p95": round(percentile(95), 2),
            "p99": round(percentile(99), 2),
            "samples": n,
        }

    def get_token_usage_trends(self, org_id: Optional[str] = None, days: int = 30) -> dict:
        self._telemetry["get_token_usage_trends_calls"] += 1
        records = self._records
        if org_id:
            records = [r for r in records if r.org_id == org_id]
        daily_prompt = defaultdict(int)
        daily_completion = defaultdict(int)
        for r in records:
            day = r.timestamp[:10]
            daily_prompt[day] += r.tokens_prompt
            daily_completion[day] += r.tokens_completion
        sorted_days = sorted(set(list(daily_prompt.keys()) + list(daily_completion.keys())), reverse=True)[:days]
        return {
            "daily_prompt_tokens": {d: daily_prompt[d] for d in sorted_days},
            "daily_completion_tokens": {d: daily_completion[d] for d in sorted_days},
            "total_prompt": sum(daily_prompt.values()),
            "total_completion": sum(daily_completion.values()),
        }


class TelemetryAnalyzer:
    def __init__(self, storage_dir: str):
        self.storage_dir = Path(storage_dir)
        self._telemetry = defaultdict(int)
        self._collector: Optional[TelemetryCollector] = None

    def set_collector(self, collector: TelemetryCollector):
        self._collector = collector

    def calculate_stats(self, org_id: Optional[str] = None, start: Optional[str] = None, end: Optional[str] = None) -> TelemetryStats:
        self._telemetry["calculate_stats_calls"] += 1
        if not self._collector:
            return TelemetryStats()
        records = self._collector.get_records(org_id=org_id, limit=100000)
        if start:
            records = [r for r in records if r.timestamp >= start]
        if end:
            records = [r for r in records if r.timestamp <= end]
        if not records:
            return TelemetryStats(period_start=start or "", period_end=end or "")

        total = len(records)
        successes = sum(1 for r in records if r.success)
        latencies = sorted(r.latency_ms for r in records if r.latency_ms > 0)
        failures = sum(1 for r in records if not r.success)
        retries = sum(1 for r in records if r.event == TelemetryEvent.RETRY)
        timeouts = sum(1 for r in records if r.event == TelemetryEvent.TIMEOUT)
        total_tokens = sum(r.tokens_prompt + r.tokens_completion for r in records)
        total_cost = sum(r.cost for r in records)

        def percentile(data, p):
            if not data:
                return 0.0
            idx = int(math.ceil(p / 100.0 * len(data))) - 1
            return data[max(0, min(idx, len(data) - 1))]

        return TelemetryStats(
            period_start=start or records[0].timestamp,
            period_end=end or records[-1].timestamp,
            total_requests=total,
            success_rate=round(successes / total * 100.0, 2) if total > 0 else 0.0,
            avg_latency_ms=round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
            p95_latency_ms=round(percentile(latencies, 95), 2),
            p99_latency_ms=round(percentile(latencies, 99), 2),
            total_tokens=total_tokens,
            total_cost=round(total_cost, 6),
            failure_count=failures,
            retry_count=retries,
            timeout_count=timeouts,
        )

    def get_success_rate(self, org_id: Optional[str] = None) -> float:
        self._telemetry["get_success_rate_calls"] += 1
        stats = self.calculate_stats(org_id=org_id)
        return stats.success_rate

    def get_error_rate(self, org_id: Optional[str] = None) -> float:
        self._telemetry["get_error_rate_calls"] += 1
        stats = self.calculate_stats(org_id=org_id)
        return round(100.0 - stats.success_rate, 2)

    def get_average_latency(self, org_id: Optional[str] = None) -> float:
        self._telemetry["get_average_latency_calls"] += 1
        stats = self.calculate_stats(org_id=org_id)
        return stats.avg_latency_ms

    def get_p95_latency(self, org_id: Optional[str] = None) -> float:
        self._telemetry["get_p95_latency_calls"] += 1
        stats = self.calculate_stats(org_id=org_id)
        return stats.p95_latency_ms

    def get_p99_latency(self, org_id: Optional[str] = None) -> float:
        self._telemetry["get_p99_latency_calls"] += 1
        stats = self.calculate_stats(org_id=org_id)
        return stats.p99_latency_ms

    def detect_anomalies(self, org_id: Optional[str] = None, window: int = 10) -> list[dict]:
        self._telemetry["detect_anomalies_calls"] += 1
        if not self._collector:
            return []
        records = self._collector.get_records(org_id=org_id, limit=10000)
        if len(records) < window:
            return []

        sorted_records = sorted(records, key=lambda r: r.timestamp)
        anomalies = []

        latencies = [r.latency_ms for r in sorted_records if r.latency_ms > 0]
        if len(latencies) >= window:
            recent = latencies[-window:]
            mean = sum(recent) / len(recent)
            variance = sum((x - mean) ** 2 for x in recent) / len(recent)
            std = math.sqrt(variance)
            threshold = mean + 3 * std
            for r in sorted_records[-window:]:
                if r.latency_ms > threshold and r.latency_ms > 0:
                    anomalies.append({
                        "type": "latency_spike",
                        "record_id": r.id,
                        "value": r.latency_ms,
                        "threshold": round(threshold, 2),
                        "timestamp": r.timestamp,
                        "model": r.model,
                        "provider": r.provider,
                    })

        recent_batch = sorted_records[-window:]
        failures = sum(1 for r in recent_batch if not r.success)
        if failures > window * 0.5:
            anomalies.append({
                "type": "high_failure_rate",
                "value": round(failures / window * 100.0, 2),
                "threshold": 50.0,
                "timestamp": sorted_records[-1].timestamp,
                "detail": f"{failures}/{window} recent requests failed",
            })

        return anomalies

    def get_trend(self, metric: str, org_id: Optional[str] = None, days: int = 30) -> dict:
        self._telemetry["get_trend_calls"] += 1
        if not self._collector:
            return {"metric": metric, "data": []}
        records = self._collector.get_records(org_id=org_id, limit=100000)
        daily = defaultdict(list)
        for r in records:
            day = r.timestamp[:10]
            daily[day].append(r)
        sorted_days = sorted(daily.keys())[-days:]
        trend_data = []
        for day in sorted_days:
            day_records = daily[day]
            if metric == "latency":
                vals = [r.latency_ms for r in day_records if r.latency_ms > 0]
                value = round(sum(vals) / len(vals), 2) if vals else 0.0
            elif metric == "requests":
                value = len(day_records)
            elif metric == "errors":
                value = sum(1 for r in day_records if not r.success)
            elif metric == "tokens":
                value = sum(r.tokens_prompt + r.tokens_completion for r in day_records)
            elif metric == "cost":
                value = round(sum(r.cost for r in day_records), 6)
            else:
                value = len(day_records)
            trend_data.append({"date": day, "value": value})
        return {"metric": metric, "data": trend_data, "days": len(sorted_days)}


class TelemetryDashboard:
    def __init__(self, storage_dir: str):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._dashboards_file = self.storage_dir / "telemetry_dashboards.json"
        self._dashboards: dict[str, DashboardDefinition] = {}
        self._telemetry = defaultdict(int)
        self._collector: Optional[TelemetryCollector] = None
        self._analyzer: Optional[TelemetryAnalyzer] = None
        self._load()

    def set_collector(self, collector: TelemetryCollector):
        self._collector = collector

    def set_analyzer(self, analyzer: TelemetryAnalyzer):
        self._analyzer = analyzer

    def _save(self):
        try:
            data = {did: d.to_dict() for did, d in self._dashboards.items()}
            self._dashboards_file.write_text(json.dumps(data, indent=2, default=str))
        except Exception as e:
            logger.error("Failed to save dashboards: %s", e, exc_info=True)
            raise

    def _load(self):
        try:
            if self._dashboards_file.exists():
                data = json.loads(self._dashboards_file.read_text())
                for did, ddata in data.items():
                    try:
                        self._dashboards[did] = DashboardDefinition.from_dict(ddata)
                    except Exception as e:
                        logger.warning("Skipping malformed dashboard %s: %s", did, e)
        except Exception as e:
            logger.error("Failed to load dashboards: %s", e, exc_info=True)

    def create_dashboard(self, dashboard: DashboardDefinition) -> DashboardDefinition:
        self._telemetry["dashboards_created"] += 1
        if dashboard.id in self._dashboards:
            raise ValueError(f"Dashboard {dashboard.id} already exists")
        self._dashboards[dashboard.id] = dashboard
        self._save()
        logger.info("Created dashboard %s: %s", dashboard.id, dashboard.name)
        return dashboard

    def get_dashboard(self, dashboard_id: str) -> Optional[DashboardDefinition]:
        self._telemetry["get_dashboard_calls"] += 1
        return self._dashboards.get(dashboard_id)

    def update_dashboard(self, dashboard_id: str, **updates) -> Optional[DashboardDefinition]:
        self._telemetry["update_dashboard_calls"] += 1
        dashboard = self._dashboards.get(dashboard_id)
        if not dashboard:
            logger.warning("Dashboard %s not found for update", dashboard_id)
            return None
        for key, val in updates.items():
            if hasattr(dashboard, key) and key not in ("id", "created_at"):
                setattr(dashboard, key, val)
        self._save()
        logger.info("Updated dashboard %s", dashboard_id)
        return dashboard

    def list_dashboards(self, metric_filter: Optional[str] = None) -> list[DashboardDefinition]:
        self._telemetry["list_dashboards_calls"] += 1
        if metric_filter:
            return [d for d in self._dashboards.values() if metric_filter in d.metrics]
        return list(self._dashboards.values())

    def get_dashboard_data(self, dashboard_id: str, org_id: Optional[str] = None) -> dict:
        self._telemetry["get_dashboard_data_calls"] += 1
        dashboard = self._dashboards.get(dashboard_id)
        if not dashboard:
            return {"error": "Dashboard not found"}
        if not self._collector or not self._analyzer:
            return {"error": "Collector/Analyzer not set"}
        data = {"dashboard": dashboard.to_dict(), "widgets": {}}
        for metric in dashboard.metrics:
            if metric == "stats":
                data["widgets"]["stats"] = self._analyzer.calculate_stats(org_id=org_id).to_dict()
            elif metric == "latency_distribution":
                data["widgets"]["latency_distribution"] = self._collector.get_latency_distribution(org_id=org_id)
            elif metric == "token_trends":
                data["widgets"]["token_trends"] = self._collector.get_token_usage_trends(org_id=org_id)
            elif metric == "failure_analytics":
                data["widgets"]["failure_analytics"] = self._collector.get_failure_analytics(org_id=org_id)
            elif metric == "model_telemetry":
                records = self._collector.get_records(org_id=org_id, limit=10000)
                models = set(r.model for r in records if r.model)
                data["widgets"]["model_telemetry"] = [
                    self._collector.get_model_telemetry(m, org_id=org_id).to_dict() for m in models
                ]
            elif metric == "anomalies":
                data["widgets"]["anomalies"] = self._analyzer.detect_anomalies(org_id=org_id)
            else:
                trend = self._analyzer.get_trend(metric, org_id=org_id)
                data["widgets"][metric] = trend
        return data

    def export_dashboard(self, dashboard_id: str, fmt: str = "json") -> Any:
        self._telemetry["export_dashboard_calls"] += 1
        dashboard = self._dashboards.get(dashboard_id)
        if not dashboard:
            return None
        if fmt == "json":
            return json.dumps(dashboard.to_dict(), indent=2, default=str)
        return dashboard.to_dict()


class TelemetryManager(TelemetryCollector, TelemetryAnalyzer, TelemetryDashboard):
    def __init__(self, storage_dir: str):
        TelemetryCollector.__init__(self, storage_dir)
        TelemetryAnalyzer.__init__(self, storage_dir)
        TelemetryDashboard.__init__(self, storage_dir)
        self.set_collector(self)
        self.set_analyzer(self)
        self._telemetry["manager_initialized"] += 1
        logger.info("TelemetryManager initialized at %s", storage_dir)

    def get_system_overview(self, org_id: Optional[str] = None) -> dict:
        self._telemetry["get_system_overview_calls"] += 1
        stats = self.calculate_stats(org_id=org_id)
        latency_dist = self.get_latency_distribution(org_id=org_id)
        failures = self.get_failure_analytics(org_id=org_id)
        records = self.get_records(org_id=org_id, limit=10000)
        models = set(r.model for r in records if r.model)
        providers = set(r.provider for r in records if r.provider)
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stats": stats.to_dict(),
            "latency_distribution": latency_dist,
            "failures": failures,
            "unique_models": len(models),
            "unique_providers": len(providers),
            "total_records": len(records),
            "anomalies": self.detect_anomalies(org_id=org_id),
        }

    def get_model_health(self, model: str, org_id: Optional[str] = None) -> dict:
        self._telemetry["get_model_health_calls"] += 1
        mt = self.get_model_telemetry(model, org_id=org_id)
        records = self.get_records(org_id=org_id, limit=10000)
        model_records = [r for r in records if r.model == model]
        latencies = [r.latency_ms for r in model_records if r.latency_ms > 0]
        recent = model_records[-50:] if len(model_records) >= 50 else model_records
        recent_success = sum(1 for r in recent if r.success)
        recent_health = round(recent_success / len(recent) * 100.0, 2) if recent else 100.0
        return {
            "model": model,
            "provider": mt.provider,
            "total_requests": mt.requests,
            "avg_latency_ms": mt.avg_latency,
            "avg_tokens": mt.avg_tokens,
            "error_rate": mt.error_rate,
            "total_cost": mt.cost,
            "last_used": mt.last_used,
            "recent_health_pct": recent_health,
            "status": "healthy" if recent_health >= 95 else "degraded" if recent_health >= 80 else "unhealthy",
            "p95_latency_ms": round(sorted(latencies)[int(len(latencies) * 0.95)] if len(latencies) > 0 else 0.0, 2),
        }

    def get_provider_health(self, provider: str, org_id: Optional[str] = None) -> dict:
        self._telemetry["get_provider_health_calls"] += 1
        pt = self.get_provider_telemetry(provider, org_id=org_id)
        records = self.get_records(org_id=org_id, limit=10000)
        provider_records = [r for r in records if r.provider == provider]
        recent = provider_records[-100:] if len(provider_records) >= 100 else provider_records
        recent_success = sum(1 for r in recent if r.success)
        recent_health = round(recent_success / len(recent) * 100.0, 2) if recent else 100.0
        timeouts = sum(1 for r in provider_records if r.event == TelemetryEvent.TIMEOUT)
        return {
            "provider": provider,
            "total_requests": pt["requests"],
            "avg_latency_ms": pt.get("avg_latency_ms", 0.0),
            "total_cost": pt.get("total_cost", 0.0),
            "error_rate": pt.get("error_rate", 0.0),
            "models_used": pt.get("models_used", []),
            "recent_health_pct": recent_health,
            "timeout_count": timeouts,
            "status": "healthy" if recent_health >= 95 else "degraded" if recent_health >= 80 else "unhealthy",
        }
