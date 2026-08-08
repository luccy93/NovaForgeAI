"""Research Observability — track model accuracy, prompt accuracy, hallucination rate, citation quality, agent runtime, experiment success, innovation velocity, research cost, token usage, benchmark history."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class ObservabilityMetric(Enum):
    MODEL_ACCURACY = "model_accuracy"
    PROMPT_ACCURACY = "prompt_accuracy"
    HALLUCINATION_RATE = "hallucination_rate"
    CITATION_QUALITY = "citation_quality"
    AGENT_RUNTIME = "agent_runtime"
    EXPERIMENT_SUCCESS = "experiment_success"
    INNOVATION_VELOCITY = "innovation_velocity"
    RESEARCH_COST = "research_cost"
    TOKEN_USAGE = "token_usage"
    BENCHMARK_HISTORY = "benchmark_history"


@dataclass
class MetricSnapshot:
    id: str
    metric: ObservabilityMetric
    value: float
    unit: str = ""
    tags: dict = field(default_factory=dict)
    source: str = ""
    recorded_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["metric"] = self.metric.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "MetricSnapshot":
        data = data.copy()
        data["metric"] = ObservabilityMetric(data.get("metric", "model_accuracy"))
        return cls(**data)


@dataclass
class ObsDashboard:
    current: dict = field(default_factory=dict)
    trends: dict = field(default_factory=dict)
    alerts: list = field(default_factory=list)
    last_updated: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)


class ResearchObservability:
    def __init__(self, storage_dir: str = "research_data/observability"):
        self.storage_dir = storage_dir
        self._snapshots: dict[str, MetricSnapshot] = {}
        self._alerts: list = []
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _snapshots_path(self) -> str: return os.path.join(self.storage_dir, "snapshots.json")
    def _alerts_path(self) -> str: return os.path.join(self.storage_dir, "alerts.json")

    def _load(self) -> None:
        for path, store in [(self._snapshots_path(), self._snapshots), (self._alerts_path(), None)]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if store is not None:
                        for k, v in data.items():
                            try: store[k] = MetricSnapshot.from_dict(v)
                            except Exception as e: logger.warning("Skipping %s: %s", k, e)
                    else:
                        self._alerts = data
                except Exception as e: logger.error("Failed to load observability: %s", e)

    def _save(self) -> None:
        try:
            with open(self._snapshots_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._snapshots.items()}, f, indent=2, default=str)
            with open(self._alerts_path(), "w", encoding="utf-8") as f:
                json.dump(self._alerts, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save observability: %s", e)

    def record_metric(self, metric: ObservabilityMetric, value: float, unit: str = "", tags: dict = None, source: str = "") -> MetricSnapshot:
        snap = MetricSnapshot(id=str(uuid.uuid4()), metric=metric, value=value, unit=unit, tags=tags or {}, source=source)
        self._snapshots[snap.id] = snap
        self._save()
        return snap

    def get_metric_history(self, metric: ObservabilityMetric, limit: int = 100) -> list[MetricSnapshot]:
        results = [s for s in self._snapshots.values() if s.metric == metric]
        return sorted(results, key=lambda s: s.recorded_at, reverse=True)[:limit]

    def get_dashboard(self) -> ObsDashboard:
        current = {}
        trends = {}
        for m in ObservabilityMetric:
            history = self.get_metric_history(m, limit=50)
            if history:
                current[m.value] = history[0].value
                if len(history) > 1:
                    values = [s.value for s in reversed(history)]
                    trends[m.value] = {
                        "current": values[-1], "avg": round(sum(values) / len(values), 4),
                        "min": min(values), "max": max(values),
                        "direction": "up" if values[-1] > values[0] else "down" if values[-1] < values[0] else "stable",
                    }
        return ObsDashboard(current=current, trends=trends, alerts=self._alerts)

    def add_alert(self, message: str, severity: str = "info", metric: str = "", threshold: float = 0.0) -> dict:
        alert = {"id": str(uuid.uuid4()), "message": message, "severity": severity, "metric": metric, "threshold": threshold, "created_at": datetime.now(timezone.utc).isoformat()}
        self._alerts.append(alert)
        self._save()
        return alert

    def get_alerts(self, severity: str = "") -> list[dict]:
        if severity: return [a for a in self._alerts if a.get("severity") == severity]
        return self._alerts

    def get_telemetry(self) -> dict: return dict(self._telemetry)
