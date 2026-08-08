"""Prompt Research — benchmark prompts on accuracy, consistency, latency, cost, hallucination, context usage, tool usage, citation quality. Maintain leaderboards, auto-identify best performers."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


PROMPT_METRICS = [
    "accuracy", "consistency", "latency", "cost",
    "hallucination", "context_usage", "tool_usage", "citation_quality",
]


@dataclass
class PromptEvalRun:
    id: str
    prompt_id: str
    prompt_name: str
    prompt_template: str = ""
    model_used: str = ""
    metrics: dict = field(default_factory=dict)
    overall_score: float = 0.0
    test_cases: int = 0
    passed: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "PromptEvalRun": return cls(**data)


@dataclass
class PromptOptimization:
    prompt_id: str
    original_score: float
    optimized_score: float
    improvement: float
    changes: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)


class PromptResearch:
    def __init__(self, storage_dir: str = "research_data/prompt_research"):
        self.storage_dir = storage_dir
        self._runs: dict[str, PromptEvalRun] = {}
        self._optimizations: list = []
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _runs_path(self) -> str: return os.path.join(self.storage_dir, "runs.json")
    def _opt_path(self) -> str: return os.path.join(self.storage_dir, "optimizations.json")

    def _load(self) -> None:
        for path, store in [(self._runs_path(), self._runs), (self._opt_path(), None)]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if store is not None:
                        for k, v in data.items():
                            try: store[k] = PromptEvalRun.from_dict(v)
                            except Exception as e: logger.warning("Skipping %s: %s", k, e)
                    else:
                        self._optimizations = [PromptOptimization(**v) if isinstance(v, dict) else v for v in data]
                except Exception as e: logger.error("Failed to load prompt research: %s", e)

    def _save(self) -> None:
        try:
            with open(self._runs_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._runs.items()}, f, indent=2, default=str)
            with open(self._opt_path(), "w", encoding="utf-8") as f:
                json.dump([o.to_dict() for o in self._optimizations], f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save prompt research: %s", e)

    def evaluate_prompt(self, prompt_name: str, prompt_template: str, model_used: str, metrics: dict) -> PromptEvalRun:
        scores = [v for v in metrics.values() if isinstance(v, (int, float))]
        overall = round(sum(scores) / len(scores), 4) if scores else 0.0
        run = PromptEvalRun(
            id=str(uuid.uuid4()), prompt_id=prompt_template[:32], prompt_name=prompt_name,
            prompt_template=prompt_template[:256], model_used=model_used,
            metrics=metrics, overall_score=overall, test_cases=len(metrics),
            passed=overall >= 0.7,
        )
        self._runs[run.id] = run
        self._save()
        return run

    def get_leaderboard(self, metric: str = "overall", top_n: int = 20) -> list[dict]:
        best_by_prompt = {}
        for r in self._runs.values():
            if r.prompt_name not in best_by_prompt or r.overall_score > best_by_prompt[r.prompt_name].overall_score:
                best_by_prompt[r.prompt_name] = r
        sorted_runs = sorted(best_by_prompt.values(), key=lambda r: getattr(r, "overall_score" if metric == "overall" else "metrics", {}).get(metric, 0.0) if metric != "overall" else r.overall_score, reverse=True)
        return [{"rank": i+1, "name": r.prompt_name, metric: (r.overall_score if metric == "overall" else r.metrics.get(metric, 0.0)), "model": r.model_used, "score": r.overall_score} for i, r in enumerate(sorted_runs[:top_n])]

    def find_best_prompt(self, metric: str = "accuracy") -> Optional[dict]:
        lb = self.get_leaderboard(metric=metric, top_n=1)
        return lb[0] if lb else None

    def record_optimization(self, prompt_id: str, original_score: float, optimized_score: float, changes: list = None) -> PromptOptimization:
        opt = PromptOptimization(prompt_id=prompt_id, original_score=original_score, optimized_score=optimized_score, improvement=round(optimized_score - original_score, 4), changes=changes or [])
        self._optimizations.append(opt)
        self._save()
        return opt

    def get_optimization_history(self) -> list[PromptOptimization]:
        return sorted(self._optimizations, key=lambda o: o.created_at, reverse=True)

    def get_telemetry(self) -> dict: return dict(self._telemetry)
