"""Model Benchmarking — evaluate models on accuracy, latency, reasoning, code generation, repo understanding, security review, documentation quality, agent perf, context understanding, tool calling."""
import json, uuid, os, logging, time
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class ModelProvider(Enum):
    OPENAI = "openai"
    CLAUDE = "claude"
    GEMINI = "gemini"
    DEEPSEEK = "deepseek"
    MISTRAL = "mistral"
    LLAMA = "llama"
    QWEN = "qwen"
    COHERE = "cohere"
    GROK = "grok"
    OPENROUTER = "openrouter"
    OLLAMA = "ollama"
    LM_STUDIO = "lm_studio"
    AWS_BEDROCK = "aws_bedrock"
    GOOGLE_VERTEX = "google_vertex"
    AZURE_OPENAI = "azure_openai"
    CUSTOM = "custom"


class BenchmarkCategory(Enum):
    ACCURACY = "accuracy"
    LATENCY = "latency"
    REASONING = "reasoning"
    CODE_GENERATION = "code_generation"
    REPO_UNDERSTANDING = "repo_understanding"
    SECURITY_REVIEW = "security_review"
    DOCUMENTATION = "documentation"
    AGENT_PERFORMANCE = "agent_performance"
    CONTEXT_UNDERSTANDING = "context_understanding"
    TOOL_CALLING = "tool_calling"


@dataclass
class ModelBenchmarkResult:
    id: str
    model_name: str
    provider: ModelProvider
    category: BenchmarkCategory
    score: float
    latency_ms: float
    tokens_used: int = 0
    cost: float = 0.0
    passed: bool = False
    errors: list = field(default_factory=list)
    details: dict = field(default_factory=dict)
    test_case: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["provider"] = self.provider.value
        d["category"] = self.category.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ModelBenchmarkResult":
        data = data.copy()
        data["provider"] = ModelProvider(data.get("provider", "custom"))
        data["category"] = BenchmarkCategory(data.get("category", "accuracy"))
        return cls(**data)


@dataclass
class ModelProfile:
    id: str
    name: str
    provider: ModelProvider
    version: str = ""
    capabilities: list = field(default_factory=list)
    context_window: int = 0
    pricing_input: float = 0.0
    pricing_output: float = 0.0
    avg_score: float = 0.0
    benchmark_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["provider"] = self.provider.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ModelProfile":
        data = data.copy()
        data["provider"] = ModelProvider(data.get("provider", "custom"))
        return cls(**data)


class ModelBenchmarking:
    def __init__(self, storage_dir: str = "research_data/model_benchmarks"):
        self.storage_dir = storage_dir
        self._results: dict[str, ModelBenchmarkResult] = {}
        self._profiles: dict[str, ModelProfile] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _results_path(self) -> str: return os.path.join(self.storage_dir, "results.json")
    def _profiles_path(self) -> str: return os.path.join(self.storage_dir, "profiles.json")

    def _load(self) -> None:
        for path, store, cls in [
            (self._results_path(), self._results, ModelBenchmarkResult),
            (self._profiles_path(), self._profiles, ModelProfile),
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
            with open(self._profiles_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._profiles.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save model benchmarks: %s", e)

    def register_model(self, name: str, provider: ModelProvider, version: str = "", capabilities: list = None, context_window: int = 0, pricing_input: float = 0.0, pricing_output: float = 0.0) -> ModelProfile:
        profile = ModelProfile(id=str(uuid.uuid4()), name=name, provider=provider, version=version, capabilities=capabilities or [], context_window=context_window, pricing_input=pricing_input, pricing_output=pricing_output)
        self._profiles[profile.id] = profile
        self._save()
        return profile

    def record_result(self, model_name: str, provider: ModelProvider, category: BenchmarkCategory, score: float, latency_ms: float, tokens_used: int = 0, cost: float = 0.0, test_case: str = "", details: dict = None) -> ModelBenchmarkResult:
        result = ModelBenchmarkResult(
            id=str(uuid.uuid4()), model_name=model_name, provider=provider, category=category,
            score=score, latency_ms=latency_ms, tokens_used=tokens_used, cost=cost,
            passed=score >= 0.7, test_case=test_case, details=details or {},
        )
        self._results[result.id] = result
        for profile in self._profiles.values():
            if profile.name == model_name:
                all_scores = [r.score for r in self._results.values() if r.model_name == model_name]
                profile.avg_score = round(sum(all_scores) / len(all_scores), 4) if all_scores else 0.0
                profile.benchmark_count = len(all_scores)
                profile.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return result

    def get_leaderboard(self, category: Optional[BenchmarkCategory] = None, top_n: int = 10) -> list[dict]:
        results = list(self._results.values())
        if category: results = [r for r in results if r.category == category]
        best_by_model = {}
        for r in results:
            key = (r.model_name, r.category.value)
            if key not in best_by_model or r.score > best_by_model[key].score:
                best_by_model[key] = r
        sorted_results = sorted(best_by_model.values(), key=lambda r: r.score, reverse=True)
        return [{"rank": i+1, "model": r.model_name, "provider": r.provider.value, "category": r.category.value, "score": r.score, "latency_ms": r.latency_ms, "cost": r.cost, "passed": r.passed} for i, r in enumerate(sorted_results[:top_n])]

    def compare_models(self, model_names: list[str], category: Optional[BenchmarkCategory] = None) -> dict:
        results = {}
        for name in model_names:
            model_results = [r for r in self._results.values() if r.model_name == name]
            if category: model_results = [r for r in model_results if r.category == category]
            if model_results:
                results[name] = {
                    "avg_score": round(sum(r.score for r in model_results) / len(model_results), 4),
                    "avg_latency_ms": round(sum(r.latency_ms for r in model_results) / len(model_results), 2),
                    "total_cost": round(sum(r.cost for r in model_results), 6),
                    "total_tests": len(model_results),
                    "passed": sum(1 for r in model_results if r.passed),
                }
        return {"comparison": results, "category": category.value if category else "all"}

    def list_profiles(self) -> list[ModelProfile]:
        return list(self._profiles.values())

    def get_telemetry(self) -> dict: return dict(self._telemetry)
