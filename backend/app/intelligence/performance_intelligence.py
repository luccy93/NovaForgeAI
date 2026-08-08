"""Performance Intelligence — tracks and analyzes performance metrics across the repository and AI operations."""

import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from threading import Lock


@dataclass
class PerformanceMetric:
    name: str
    value: float
    unit: str  # ms, MB, %, req/s, tokens/s
    timestamp: str
    threshold: Optional[float] = None
    is_anomaly: bool = False
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class QueryProfile:
    query: str
    duration_ms: float
    timestamp: str
    source: str = ""
    row_count: int = 0
    is_slow: bool = False


@dataclass
class MemoryProfile:
    object_type: str
    size_mb: float
    count: int
    location: str = ""


@dataclass
class PerformanceReport:
    repo_id: str
    repo_name: str
    timestamp: str
    metrics: list[PerformanceMetric] = field(default_factory=list)
    slow_queries: list[QueryProfile] = field(default_factory=list)
    memory_profile: list[MemoryProfile] = field(default_factory=list)
    ai_latency: dict[str, float] = field(default_factory=dict)
    optimization_recommendations: list[dict] = field(default_factory=list)
    overall_performance_score: float = 0.0


class PerformanceIntelligence:
    """Tracks performance metrics, detects anomalies, and generates optimization recommendations."""

    _instance = None
    _lock = Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, repo_path: str = ""):
        if self._initialized:
            return
        self._initialized = True
        self.repo_path = Path(repo_path) if repo_path else Path()
        self.metrics: list[PerformanceMetric] = []
        self.queries: list[QueryProfile] = []
        self._lock = Lock()

    def record_metric(self, name: str, value: float, unit: str = "",
                      threshold: Optional[float] = None, tags: dict = None):
        with self._lock:
            metric = PerformanceMetric(
                name=name,
                value=value,
                unit=unit,
                timestamp=datetime.now(timezone.utc).isoformat(),
                threshold=threshold,
                is_anomaly=threshold is not None and value > threshold,
                tags=tags or {},
            )
            self.metrics.append(metric)
            if len(self.metrics) > 10000:
                self.metrics = self.metrics[-10000:]
            return metric

    def profile_query(self, query: str, duration_ms: float, source: str = "",
                      row_count: int = 0, slow_threshold_ms: float = 500.0):
        with self._lock:
            profile = QueryProfile(
                query=query[:200],
                duration_ms=round(duration_ms, 2),
                timestamp=datetime.now(timezone.utc).isoformat(),
                source=source,
                row_count=row_count,
                is_slow=duration_ms > slow_threshold_ms,
            )
            self.queries.append(profile)
            if profile.is_slow:
                self.record_metric("slow_query", duration_ms, "ms",
                                   threshold=slow_threshold_ms,
                                   tags={"query": query[:50], "source": source})
            if len(self.queries) > 5000:
                self.queries = self.queries[-5000:]
            return profile

    def analyze(self) -> PerformanceReport:
        report = PerformanceReport(
            repo_id=str(hash(str(self.repo_path))),
            repo_name=self.repo_path.name,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        self._analyze_codebase_performance(report)
        self._analyze_query_performance(report)
        self._analyze_memory_usage(report)
        self._analyze_ai_latency(report)
        self._generate_recommendations(report)
        report.overall_performance_score = self._calculate_score(report)

        return report

    def _analyze_codebase_performance(self, report: PerformanceReport):
        large_objects = []
        nested_loops = 0
        async_usage = 0
        cache_usage = 0

        for f in self.repo_path.rglob("*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                lines = content.count("\n") + 1
            except Exception:
                continue

            rel = str(f.relative_to(self.repo_path))

            if lines > 500:
                large_objects.append({"file": rel, "lines": lines, "type": "large_file"})

            if re.search(r'for\s+\w+\s+in\s+.*:\s*\n\s+for\s+\w+\s+in\s+', content):
                nested_loops += 1

            if re.search(r'async\s+def|asyncio\.run|await\s', content):
                async_usage += 1

            if re.search(r'@(lru_cache|cache)|functools\.lru_cache|functools\.cache', content):
                cache_usage += 1

        for obj in large_objects[:10]:
            report.memory_profile.append(MemoryProfile(
                object_type="large_file",
                size_mb=round(obj["lines"] * 0.05, 2),
                count=1,
                location=obj["file"],
            ))

        report.metrics.append(PerformanceMetric(
            name="nested_loops_count", value=nested_loops, unit="count",
            timestamp=datetime.now(timezone.utc).isoformat(),
            threshold=5, is_anomaly=nested_loops > 5,
        ))
        report.metrics.append(PerformanceMetric(
            name="async_functions", value=async_usage, unit="count",
            timestamp=datetime.now(timezone.utc).isoformat(),
        ))
        report.metrics.append(PerformanceMetric(
            name="cache_usage", value=cache_usage, unit="count",
            timestamp=datetime.now(timezone.utc).isoformat(),
        ))
        report.metrics.append(PerformanceMetric(
            name="large_files", value=len(large_objects), unit="count",
            timestamp=datetime.now(timezone.utc).isoformat(),
            threshold=3, is_anomaly=len(large_objects) > 3,
        ))

    def _analyze_query_performance(self, report: PerformanceReport):
        if not self.queries:
            return

        slow = [q for q in self.queries if q.is_slow]
        report.slow_queries = slow[-50:]

        avg_duration = sum(q.duration_ms for q in self.queries) / len(self.queries)
        p95 = sorted(q.duration_ms for q in self.queries)[int(len(self.queries) * 0.95)]

        report.metrics.append(PerformanceMetric(
            name="avg_query_duration_ms", value=round(avg_duration, 2), unit="ms",
            timestamp=datetime.now(timezone.utc).isoformat(),
            threshold=200, is_anomaly=avg_duration > 200,
        ))
        report.metrics.append(PerformanceMetric(
            name="p95_query_duration_ms", value=round(p95, 2), unit="ms",
            timestamp=datetime.now(timezone.utc).isoformat(),
            threshold=1000, is_anomaly=p95 > 1000,
        ))
        report.metrics.append(PerformanceMetric(
            name="slow_query_count", value=len(slow), unit="count",
            timestamp=datetime.now(timezone.utc).isoformat(),
        ))

    def _analyze_memory_usage(self, report: PerformanceReport):
        data_files = list(self.repo_path.rglob("*.pkl")) + list(self.repo_path.rglob("*.h5")) + \
                     list(self.repo_path.rglob("*.npy")) + list(self.repo_path.rglob("*.parquet")) + \
                     list(self.repo_path.rglob("*.joblib"))

        total_mb = 0
        for df in data_files[:20]:
            try:
                size_mb = df.stat().st_size / (1024 * 1024)
                total_mb += size_mb
                report.memory_profile.append(MemoryProfile(
                    object_type="data_file",
                    size_mb=round(size_mb, 2),
                    count=1,
                    location=str(df.relative_to(self.repo_path)),
                ))
            except Exception:
                pass

        report.metrics.append(PerformanceMetric(
            name="data_storage_mb", value=round(total_mb, 2), unit="MB",
            timestamp=datetime.now(timezone.utc).isoformat(),
            threshold=500, is_anomaly=total_mb > 500,
        ))

    def _analyze_ai_latency(self, report: PerformanceReport):
        ai_metrics = [m for m in self.metrics if "ai" in m.name.lower() or "llm" in m.name.lower() or "embedding" in m.name.lower()]

        latency_names = {"ai_embedding_ms": 0, "ai_search_ms": 0, "ai_completion_ms": 0, "ai_analysis_ms": 0}
        for m in ai_metrics:
            if m.name in latency_names:
                latency_names[m.name] = m.value

        report.ai_latency = latency_names

        for name, val in latency_names.items():
            if val > 0:
                thresholds = {
                    "ai_embedding_ms": 500,
                    "ai_search_ms": 2000,
                    "ai_completion_ms": 10000,
                    "ai_analysis_ms": 30000,
                }
                report.metrics.append(PerformanceMetric(
                    name=name, value=val, unit="ms",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    threshold=thresholds.get(name),
                    is_anomaly=val > thresholds.get(name, float('inf')),
                ))

    def _generate_recommendations(self, report: PerformanceReport):
        for m in report.metrics:
            if m.is_anomaly:
                recommendation = self._recommendation_for(m)
                if recommendation:
                    report.optimization_recommendations.append(recommendation)

        if not report.optimization_recommendations:
            report.optimization_recommendations.append({
                "area": "performance",
                "message": "No significant performance issues detected",
                "priority": "low",
            })

    def _recommendation_for(self, metric: PerformanceMetric) -> Optional[dict]:
        recommendations = {
            "slow_query_count": {
                "area": "database",
                "message": f"Query performance needs attention",
                "priority": "high",
                "action": "Review slow queries, add indexes, optimize query patterns",
            },
            "avg_query_duration_ms": {
                "area": "database",
                "message": f"Average query duration ({metric.value}ms) exceeds threshold",
                "priority": "medium",
                "action": "Profile queries, review N+1 patterns, add caching layer",
            },
            "p95_query_duration_ms": {
                "area": "database",
                "message": f"P95 query latency at {metric.value}ms — user-facing impact likely",
                "priority": "high",
                "action": "Identify and optimize slowest 5% of queries",
            },
            "nested_loops_count": {
                "area": "code",
                "message": f"{int(metric.value)} files with nested loops detected",
                "priority": "medium",
                "action": "Replace nested loops with vectorized operations or dictionary lookups",
            },
            "large_files": {
                "area": "code",
                "message": f"{int(metric.value)} large files detected — potential memory pressure",
                "priority": "low",
                "action": "Split large files into smaller modules",
            },
            "data_storage_mb": {
                "area": "storage",
                "message": f"Data storage at {metric.value}MB",
                "priority": "medium",
                "action": "Review data retention, compress or archive old data",
            },
        }
        base = recommendations.get(metric.name)
        if base:
            return {**base, "metric_value": metric.value, "threshold": metric.threshold}
        return None

    def _calculate_score(self, report: PerformanceReport) -> float:
        score = 100.0
        for m in report.metrics:
            if m.is_anomaly:
                if m.name in ("avg_query_duration_ms", "p95_query_duration_ms"):
                    score -= 15
                elif m.name in ("slow_query_count", "nested_loops_count"):
                    score -= 10
                elif m.name in ("data_storage_mb", "large_files"):
                    score -= 5
                else:
                    score -= 3
        return max(0, round(score, 2))

    def get_trend(self, metric_name: str, limit: int = 100) -> list[PerformanceMetric]:
        return [m for m in self.metrics if m.name == metric_name][-limit:]

    def get_recent_alerts(self, limit: int = 20) -> list[PerformanceMetric]:
        return sorted(
            [m for m in self.metrics if m.is_anomaly],
            key=lambda x: x.timestamp, reverse=True
        )[:limit]
