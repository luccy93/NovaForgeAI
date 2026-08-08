"""Evaluation Framework — automatically evaluate models, agents, prompts, RAG, embeddings, search, memory, tool calling, repository intelligence, architecture understanding, security analysis."""
import json, uuid, os, logging, math
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional, Callable
from enum import Enum

logger = logging.getLogger(__name__)


class EvaluationTarget(Enum):
    MODEL = "model"
    AGENT = "agent"
    PROMPT = "prompt"
    EMBEDDING = "embedding"
    SEARCH = "search"
    MEMORY = "memory"
    TOOL = "tool"
    RAG = "rag"
    REPO_INTELLIGENCE = "repo_intelligence"
    ARCHITECTURE = "architecture"
    SECURITY = "security"
    CITATION = "citation"


class EvaluationStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class EvalMetric:
    name: str
    value: float
    weight: float = 1.0
    threshold: Optional[float] = None
    passed: Optional[bool] = None
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict: return asdict(self)


@dataclass
class EvalResult:
    id: str
    target_id: str
    target_type: EvaluationTarget
    status: EvaluationStatus
    metrics: list = field(default_factory=list)
    score: float = 0.0
    passed: bool = False
    errors: list = field(default_factory=list)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["target_type"] = self.target_type.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "EvalResult":
        data = data.copy()
        data["target_type"] = EvaluationTarget(data.get("target_type", "model"))
        data["status"] = EvaluationStatus(data.get("status", "pending"))
        return cls(**data)


@dataclass
class EvalSuite:
    id: str
    name: str
    description: str = ""
    target_types: list = field(default_factory=list)
    metrics_config: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "EvalSuite": return cls(**data)


class EvaluationFramework:
    def __init__(self, storage_dir: str = "research_data/evaluations"):
        self.storage_dir = storage_dir
        self._results: dict[str, EvalResult] = {}
        self._suites: dict[str, EvalSuite] = {}
        self._evaluators: dict[str, Callable] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _results_path(self) -> str: return os.path.join(self.storage_dir, "results.json")
    def _suites_path(self) -> str: return os.path.join(self.storage_dir, "suites.json")

    def _load(self) -> None:
        for path, store, cls in [
            (self._results_path(), self._results, EvalResult),
            (self._suites_path(), self._suites, EvalSuite),
        ]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = cls.from_dict(v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Failed to load %s: %s", path, e)

    def _save(self) -> None:
        try:
            with open(self._results_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._results.items()}, f, indent=2, default=str)
            with open(self._suites_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._suites.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save evaluations: %s", e)

    def register_evaluator(self, name: str, fn: Callable) -> None:
        self._evaluators[name] = fn

    def create_suite(self, name: str, description: str = "", target_types: list = None, metrics_config: list = None) -> EvalSuite:
        suite = EvalSuite(id=str(uuid.uuid4()), name=name, description=description, target_types=target_types or [], metrics_config=metrics_config or [])
        self._suites[suite.id] = suite
        self._save()
        return suite

    def evaluate(self, target_id: str, target_type: EvaluationTarget, evaluator_name: str = "default", params: dict = None) -> EvalResult:
        result = EvalResult(id=str(uuid.uuid4()), target_id=target_id, target_type=target_type, status=EvaluationStatus.RUNNING, started_at=datetime.now(timezone.utc).isoformat())
        self._results[result.id] = result
        self._save()
        try:
            fn = self._evaluators.get(evaluator_name)
            if fn:
                metrics_data = fn(target_id, target_type, params or {})
            else:
                metrics_data = self._default_evaluate(target_id, target_type, params or {})
            result.metrics = [EvalMetric(**m) if isinstance(m, dict) else m for m in metrics_data.get("metrics", [])]
            weighted_sum = sum(m.value * m.weight for m in result.metrics)
            total_weight = sum(m.weight for m in result.metrics)
            result.score = round(weighted_sum / max(total_weight, 1), 4)
            result.passed = all(
                (m.threshold is None or m.value >= m.threshold) for m in result.metrics
            ) if result.metrics else True
            result.status = EvaluationStatus.COMPLETED
        except Exception as e:
            result.status = EvaluationStatus.FAILED
            result.errors.append(str(e))
            logger.error("Evaluation failed for %s: %s", target_id, e)
        result.completed_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return result

    def _default_evaluate(self, target_id: str, target_type: EvaluationTarget, params: dict) -> dict:
        return {"metrics": [{"name": "completeness", "value": 1.0, "weight": 1.0}]}

    def get_result(self, result_id: str) -> Optional[EvalResult]: return self._results.get(result_id)

    def compare(self, result_ids: list[str]) -> dict:
        results = [self._results.get(rid) for rid in result_ids]
        results = [r for r in results if r]
        comparison = {"results": [r.to_dict() for r in results]}
        if results:
            scores = [r.score for r in results]
            comparison["summary"] = {
                "best_score": max(scores), "worst_score": min(scores),
                "avg_score": round(sum(scores) / len(scores), 4),
                "best_id": results[scores.index(max(scores))].id,
            }
        return comparison

    def list_results(self, target_type: Optional[EvaluationTarget] = None, limit: int = 50) -> list[EvalResult]:
        results = list(self._results.values())
        if target_type: results = [r for r in results if r.target_type == target_type]
        results.sort(key=lambda r: r.created_at, reverse=True)
        return results[:limit]

    def get_leaderboard(self, target_type: EvaluationTarget, top_n: int = 10) -> list[dict]:
        results = [r for r in self._results.values() if r.target_type == target_type and r.status == EvaluationStatus.COMPLETED]
        best_by_target = {}
        for r in results:
            if r.target_id not in best_by_target or r.score > best_by_target[r.target_id].score:
                best_by_target[r.target_id] = r
        sorted_results = sorted(best_by_target.values(), key=lambda r: r.score, reverse=True)
        return [{"rank": i+1, "target_id": r.target_id, "score": r.score, "passed": r.passed, "metrics": [m.to_dict() for m in r.metrics]} for i, r in enumerate(sorted_results[:top_n])]

    def get_telemetry(self) -> dict: return dict(self._telemetry)
