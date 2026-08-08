"""Model Research — continuously evaluate OpenAI, Claude, Gemini, DeepSeek, Mistral, Llama, Qwen, Cohere, Grok, OpenRouter, Ollama, LM Studio, AWS Bedrock, Google Vertex, Azure OpenAI across accuracy, latency, reasoning, code generation, repo understanding, security review, documentation quality, agent perf, context understanding, tool calling."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


MODEL_PROVIDERS = [
    "openai", "claude", "gemini", "deepseek", "mistral", "llama", "qwen",
    "cohere", "grok", "openrouter", "ollama", "lm_studio", "aws_bedrock",
    "google_vertex", "azure_openai",
]

EVALUATION_DIMENSIONS = [
    "accuracy", "latency", "reasoning", "code_generation",
    "repo_understanding", "security_review", "documentation_quality",
    "agent_performance", "context_understanding", "tool_calling",
]


@dataclass
class ModelEvalRun:
    id: str
    model_name: str
    provider: str
    version: str = ""
    dimensions: dict = field(default_factory=dict)
    overall_score: float = 0.0
    latency_ms: float = 0.0
    tokens_used: int = 0
    cost: float = 0.0
    test_cases: int = 0
    passed: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "ModelEvalRun": return cls(**data)


@dataclass
class ModelEvalSummary:
    model_name: str
    provider: str
    avg_overall: float = 0.0
    avg_latency_ms: float = 0.0
    avg_cost: float = 0.0
    total_runs: int = 0
    last_evaluated: str = ""
    dimension_averages: dict = field(default_factory=dict)

    def to_dict(self) -> dict: return asdict(self)


class ModelResearch:
    def __init__(self, storage_dir: str = "research_data/model_research"):
        self.storage_dir = storage_dir
        self._runs: dict[str, ModelEvalRun] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _store_path(self) -> str: return os.path.join(self.storage_dir, "runs.json")

    def _load(self) -> None:
        path = self._store_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    try: self._runs[k] = ModelEvalRun.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Failed to load model research: %s", e)

    def _save(self) -> None:
        try:
            with open(self._store_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._runs.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save model research: %s", e)

    def record_evaluation(self, model_name: str, provider: str, dimensions: dict, latency_ms: float = 0.0, tokens_used: int = 0, cost: float = 0.0, version: str = "") -> ModelEvalRun:
        scores = [v for v in dimensions.values() if isinstance(v, (int, float))]
        overall = round(sum(scores) / len(scores), 4) if scores else 0.0
        run = ModelEvalRun(
            id=str(uuid.uuid4()), model_name=model_name, provider=provider, version=version,
            dimensions=dimensions, overall_score=overall, latency_ms=latency_ms,
            tokens_used=tokens_used, cost=cost, test_cases=len(dimensions),
            passed=overall >= 0.7,
        )
        self._runs[run.id] = run
        self._save()
        return run

    def get_summary(self, model_name: str = "") -> list[ModelEvalSummary]:
        by_model = {}
        for run in self._runs.values():
            if model_name and run.model_name != model_name: continue
            key = f"{run.model_name}@{run.provider}"
            if key not in by_model: by_model[key] = []
            by_model[key].append(run)
        summaries = []
        for key, runs in by_model.items():
            n = len(runs)
            dims = {}
            for r in runs:
                for d, v in r.dimensions.items():
                    if d not in dims: dims[d] = []
                    dims[d].append(v)
            summaries.append(ModelEvalSummary(
                model_name=runs[0].model_name, provider=runs[0].provider,
                avg_overall=round(sum(r.overall_score for r in runs) / n, 4),
                avg_latency_ms=round(sum(r.latency_ms for r in runs) / n, 2),
                avg_cost=round(sum(r.cost for r in runs) / n, 6),
                total_runs=n, last_evaluated=max(r.created_at for r in runs),
                dimension_averages={d: round(sum(vs) / len(vs), 4) for d, vs in dims.items()},
            ))
        return summaries

    def get_leaderboard(self, dimension: str = "overall") -> list[dict]:
        summaries = self.get_summary()
        if dimension == "overall":
            sorted_s = sorted(summaries, key=lambda s: s.avg_overall, reverse=True)
            return [{"rank": i+1, "model": s.model_name, "provider": s.provider, "score": s.avg_overall, "runs": s.total_runs} for i, s in enumerate(sorted_s)]
        else:
            valid = [s for s in summaries if dimension in s.dimension_averages]
            sorted_s = sorted(valid, key=lambda s: s.dimension_averages[dimension], reverse=True)
            return [{"rank": i+1, "model": s.model_name, "provider": s.provider, "score": s.dimension_averages[dimension], "runs": s.total_runs} for i, s in enumerate(sorted_s)]

    def get_model_history(self, model_name: str) -> list[ModelEvalRun]:
        results = [r for r in self._runs.values() if r.model_name == model_name]
        return sorted(results, key=lambda r: r.created_at, reverse=True)

    def get_telemetry(self) -> dict: return dict(self._telemetry)
