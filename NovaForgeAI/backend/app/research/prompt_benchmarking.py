"""Prompt Benchmarking — benchmark prompts on accuracy, consistency, latency, cost, hallucination, context usage, tool usage, citation quality. Maintain leaderboards, auto-identify best performers."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class PromptMetric(Enum):
    ACCURACY = "accuracy"
    CONSISTENCY = "consistency"
    LATENCY = "latency"
    COST = "cost"
    HALLUCINATION = "hallucination"
    CONTEXT_USAGE = "context_usage"
    TOOL_USAGE = "tool_usage"
    CITATION_QUALITY = "citation_quality"


@dataclass
class PromptTestCase:
    id: str
    prompt_template: str
    expected_output: str = ""
    variables: dict = field(default_factory=dict)
    tags: list = field(default_factory=list)

    def to_dict(self) -> dict: return asdict(self)


@dataclass
class PromptBenchmarkResult:
    id: str
    prompt_id: str
    prompt_name: str
    metrics: dict = field(default_factory=dict)
    overall_score: float = 0.0
    rank: int = 0
    test_count: int = 0
    passed: bool = False
    model_used: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PromptBenchmarkResult":
        return cls(**data)


@dataclass
class PromptLeaderboardEntry:
    id: str
    prompt_name: str
    prompt_template: str
    overall_score: float
    rank: int
    metrics: dict = field(default_factory=dict)
    test_count: int = 0
    last_benchmarked: str = ""

    def to_dict(self) -> dict: return asdict(self)


class PromptBenchmarking:
    def __init__(self, storage_dir: str = "research_data/prompt_benchmarks"):
        self.storage_dir = storage_dir
        self._test_cases: dict[str, PromptTestCase] = {}
        self._results: dict[str, PromptBenchmarkResult] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _cases_path(self) -> str: return os.path.join(self.storage_dir, "test_cases.json")
    def _results_path(self) -> str: return os.path.join(self.storage_dir, "results.json")

    def _load(self) -> None:
        for path, store, cls in [
            (self._cases_path(), self._test_cases, PromptTestCase),
            (self._results_path(), self._results, PromptBenchmarkResult),
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
            with open(self._cases_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._test_cases.items()}, f, indent=2, default=str)
            with open(self._results_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._results.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save prompt benchmarks: %s", e)

    def add_test_case(self, prompt_template: str, expected_output: str = "", variables: dict = None, tags: list = None) -> PromptTestCase:
        tc = PromptTestCase(id=str(uuid.uuid4()), prompt_template=prompt_template, expected_output=expected_output, variables=variables or {}, tags=tags or [])
        self._test_cases[tc.id] = tc
        self._save()
        return tc

    def run_benchmark(self, prompt_name: str, prompt_template: str, model_used: str = "", scores: dict = None) -> PromptBenchmarkResult:
        scores = scores or {}
        metrics = {}
        for m in PromptMetric:
            metrics[m.value] = scores.get(m.value, 0.0)
        overall = sum(metrics.values()) / max(len(metrics), 1)
        result = PromptBenchmarkResult(
            id=str(uuid.uuid4()), prompt_id=prompt_template[:32], prompt_name=prompt_name,
            metrics=metrics, overall_score=round(overall, 4), test_count=len(self._test_cases),
            passed=overall >= 0.7, model_used=model_used,
        )
        self._results[result.id] = result
        self._save()
        return result

    def get_leaderboard(self, top_n: int = 20) -> list[PromptLeaderboardEntry]:
        best_by_prompt = {}
        for r in self._results.values():
            if r.prompt_name not in best_by_prompt or r.overall_score > best_by_prompt[r.prompt_name].overall_score:
                best_by_prompt[r.prompt_name] = r
        sorted_results = sorted(best_by_prompt.values(), key=lambda r: r.overall_score, reverse=True)
        return [PromptLeaderboardEntry(
            id=str(uuid.uuid4()), prompt_name=r.prompt_name, prompt_template=r.prompt_id,
            overall_score=r.overall_score, rank=i+1, metrics=r.metrics,
            test_count=r.test_count, last_benchmarked=r.created_at,
        ) for i, r in enumerate(sorted_results[:top_n])]

    def find_best_prompt(self, metric: str = "overall") -> Optional[PromptLeaderboardEntry]:
        lb = self.get_leaderboard(top_n=1)
        return lb[0] if lb else None

    def list_results(self, limit: int = 50) -> list[PromptBenchmarkResult]:
        results = sorted(self._results.values(), key=lambda r: r.created_at, reverse=True)
        return results[:limit]

    def get_telemetry(self) -> dict: return dict(self._telemetry)
