"""Multi-Model Orchestration — automatically selects the best model based on task, latency, cost, context size, accuracy, availability, with fallback strategy."""

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, Callable


class TaskType(Enum):
    CODE_GENERATION = "code_generation"
    CODE_REVIEW = "code_review"
    EXPLANATION = "explanation"
    SEARCH = "search"
    EMBEDDING = "embedding"
    CLASSIFICATION = "classification"
    SUMMARIZATION = "summarization"
    CHAT = "chat"
    ANALYSIS = "analysis"
    REFACTORING = "refactoring"


@dataclass
class ModelCapability:
    model_id: str
    provider: str  # openai, anthropic, google, local
    display_name: str
    task_types: list[TaskType] = field(default_factory=list)
    max_context: int = 4096
    latency_p50_ms: float = 1000.0
    cost_per_1k_input: float = 0.01
    cost_per_1k_output: float = 0.03
    accuracy_score: float = 0.8
    is_available: bool = True
    supports_streaming: bool = False
    supports_functions: bool = False
    supports_vision: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelSelection:
    task: TaskType
    primary: ModelCapability
    fallback: Optional[ModelCapability] = None
    selection_reason: str = ""
    estimated_cost: float = 0.0
    estimated_latency_ms: float = 0.0
    confidence: float = 0.0


@dataclass
class OrchestrationResult:
    selected_model: str
    fallback_used: bool = False
    actual_latency_ms: float = 0.0
    actual_cost: float = 0.0
    tokens_used: int = 0
    success: bool = True
    error: Optional[str] = None


@dataclass
class ModelRegistryReport:
    repo_id: str
    repo_name: str
    timestamp: str
    models: list[ModelCapability] = field(default_factory=list)
    selections: list[ModelSelection] = field(default_factory=list)
    total_calls: int = 0
    fallback_rate: float = 0.0
    avg_latency_ms: float = 0.0
    avg_cost: float = 0.0
    recommendations: list[str] = field(default_factory=list)


class MultiModelOrchestration:
    """Intelligent model selection — chooses optimal model based on task requirements, latency, cost, accuracy, and availability."""

    AVAILABLE_MODELS = [
        ModelCapability(
            model_id="gpt-4", provider="openai", display_name="GPT-4",
            task_types=[TaskType.CODE_REVIEW, TaskType.ANALYSIS, TaskType.REFACTORING],
            max_context=8192, latency_p50_ms=3000, cost_per_1k_input=0.03, cost_per_1k_output=0.06,
            accuracy_score=0.95, supports_streaming=True, supports_functions=True,
        ),
        ModelCapability(
            model_id="gpt-4-turbo", provider="openai", display_name="GPT-4 Turbo",
            task_types=[TaskType.CODE_GENERATION, TaskType.CODE_REVIEW, TaskType.ANALYSIS,
                        TaskType.SUMMARIZATION, TaskType.CHAT, TaskType.REFACTORING],
            max_context=128000, latency_p50_ms=2000, cost_per_1k_input=0.01, cost_per_1k_output=0.03,
            accuracy_score=0.93, supports_streaming=True, supports_functions=True,
        ),
        ModelCapability(
            model_id="gpt-3.5-turbo", provider="openai", display_name="GPT-3.5 Turbo",
            task_types=[TaskType.CHAT, TaskType.EXPLANATION, TaskType.CLASSIFICATION,
                        TaskType.SUMMARIZATION, TaskType.SEARCH],
            max_context=16384, latency_p50_ms=500, cost_per_1k_input=0.001, cost_per_1k_output=0.002,
            accuracy_score=0.85, supports_streaming=True, supports_functions=True,
        ),
        ModelCapability(
            model_id="claude-3-opus", provider="anthropic", display_name="Claude 3 Opus",
            task_types=[TaskType.CODE_REVIEW, TaskType.ANALYSIS, TaskType.REFACTORING],
            max_context=200000, latency_p50_ms=4000, cost_per_1k_input=0.015, cost_per_1k_output=0.075,
            accuracy_score=0.96, supports_streaming=True,
        ),
        ModelCapability(
            model_id="claude-3-sonnet", provider="anthropic", display_name="Claude 3 Sonnet",
            task_types=[TaskType.CODE_GENERATION, TaskType.EXPLANATION, TaskType.ANALYSIS,
                        TaskType.CHAT, TaskType.SUMMARIZATION],
            max_context=200000, latency_p50_ms=1500, cost_per_1k_input=0.003, cost_per_1k_output=0.015,
            accuracy_score=0.90, supports_streaming=True,
        ),
        ModelCapability(
            model_id="text-embedding-3-small", provider="openai", display_name="Text Embedding 3 Small",
            task_types=[TaskType.EMBEDDING], max_context=8191, latency_p50_ms=200,
            cost_per_1k_input=0.00002, cost_per_1k_output=0.0, accuracy_score=0.92,
        ),
        ModelCapability(
            model_id="text-embedding-3-large", provider="openai", display_name="Text Embedding 3 Large",
            task_types=[TaskType.EMBEDDING], max_context=8191, latency_p50_ms=300,
            cost_per_1k_input=0.00013, cost_per_1k_output=0.0, accuracy_score=0.96,
        ),
    ]

    def __init__(self):
        self.models: dict[str, ModelCapability] = {m.model_id: m for m in self.AVAILABLE_MODELS}
        self._selection_history: list[ModelSelection] = []
        self._execution_history: list[OrchestrationResult] = []
        self._custom_models: dict[str, ModelCapability] = {}
        self._scorers: dict[str, Callable] = {}

    def register_model(self, model: ModelCapability):
        self._custom_models[model.model_id] = model
        self.models[model.model_id] = model

    def register_scorer(self, task_type: TaskType, scorer_fn: Callable):
        self._scorers[task_type.value] = scorer_fn

    def select(self, task: TaskType, requirements: dict = None) -> ModelSelection:
        requirements = requirements or {}
        candidates = [m for m in self.models.values()
                     if task in m.task_types and m.is_available]

        if not candidates:
            candidates = [m for m in self.models.values() if m.is_available]

        if not candidates:
            raise ValueError(f"No available models for task: {task.value}")

        scored = []
        for model in candidates:
            score = self._score_model(model, task, requirements)
            scored.append((score, model))

        scored.sort(key=lambda x: -x[0])

        primary = scored[0][1]
        fallback = scored[1][1] if len(scored) > 1 else None

        selection = ModelSelection(
            task=task,
            primary=primary,
            fallback=fallback,
            selection_reason=self._generate_reason(primary, scored[0][0], task),
            estimated_cost=self._estimate_cost(primary, requirements.get("estimated_tokens", 500)),
            estimated_latency_ms=primary.latency_p50_ms,
            confidence=round(scored[0][0] / 100, 2),
        )

        self._selection_history.append(selection)
        return selection

    def _score_model(self, model: ModelCapability, task: TaskType, requirements: dict) -> float:
        score = 50.0

        accuracy_weight = requirements.get("accuracy_weight", 1.0)
        latency_weight = requirements.get("latency_weight", 1.0)
        cost_weight = requirements.get("cost_weight", 1.0)

        score += model.accuracy_score * 30 * accuracy_weight

        latency_score = max(0, 1 - (model.latency_p50_ms / 10000))
        score += latency_score * 15 * latency_weight

        cost_score = max(0, 1 - (model.cost_per_1k_input / 0.10))
        score += cost_score * 15 * cost_weight

        if task == TaskType.EMBEDDING and model.max_context >= requirements.get("context_size", 512):
            score += 20

        if requirements.get("needs_streaming") and model.supports_streaming:
            score += 10
        if requirements.get("needs_functions") and model.supports_functions:
            score += 10

        scorer = self._scorers.get(task.value)
        if scorer:
            score += scorer(model, requirements) * 10

        return score

    def _generate_reason(self, model: ModelCapability, score: float, task: TaskType) -> str:
        factors = []
        if model.accuracy_score > 0.9:
            factors.append("high accuracy")
        if model.latency_p50_ms < 1000:
            factors.append("low latency")
        if model.cost_per_1k_input < 0.01:
            factors.append("low cost")
        if model.max_context > 32000:
            factors.append("large context window")
        return f"Selected {model.display_name} for {task.value}: {', '.join(factors)}"

    def _estimate_cost(self, model: ModelCapability, estimated_tokens: int) -> float:
        input_cost = (estimated_tokens / 1000) * model.cost_per_1k_input
        output_cost = (estimated_tokens / 1000) * model.cost_per_1k_output
        return round(input_cost + output_cost, 6)

    def execute(self, selection: ModelSelection, handler: Callable, **kwargs) -> OrchestrationResult:
        start = datetime.now()
        result = OrchestrationResult(selected_model=selection.primary.model_id)

        try:
            output = handler(selection.primary.model_id, **kwargs)
            result.success = True
            result.tokens_used = kwargs.get("estimated_tokens", 0)
        except Exception as e:
            if selection.fallback:
                try:
                    result.selected_model = selection.fallback.model_id
                    result.fallback_used = True
                    output = handler(selection.fallback.model_id, **kwargs)
                    result.success = True
                    result.tokens_used = kwargs.get("estimated_tokens", 0)
                except Exception as e2:
                    result.success = False
                    result.error = str(e2)
            else:
                result.success = False
                result.error = str(e)

        result.actual_latency_ms = (datetime.now() - start).total_seconds() * 1000
        model = self.models.get(result.selected_model)
        if model:
            result.actual_cost = self._estimate_cost(model, result.tokens_used)

        self._execution_history.append(result)
        return result

    def execute_with_fallback(self, task: TaskType, handler: Callable, requirements: dict = None, **kwargs) -> OrchestrationResult:
        selection = self.select(task, requirements)
        return self.execute(selection, handler, **kwargs)

    def get_fallback_rate(self) -> float:
        if not self._execution_history:
            return 0.0
        return sum(1 for r in self._execution_history if r.fallback_used) / len(self._execution_history)

    def get_average_latency(self) -> float:
        if not self._execution_history:
            return 0.0
        return sum(r.actual_latency_ms for r in self._execution_history if r.success) / max(
            sum(1 for r in self._execution_history if r.success), 1)

    def get_average_cost(self) -> float:
        if not self._execution_history:
            return 0.0
        return sum(r.actual_cost for r in self._execution_history) / len(self._execution_history)

    def generate_report(self) -> ModelRegistryReport:
        report = ModelRegistryReport(
            repo_id=str(hash(str(self))),
            repo_name="Multi-Model Orchestrator",
            timestamp=datetime.now(timezone.utc).isoformat(),
            models=list(self.models.values()),
            selections=self._selection_history[-100:],
            total_calls=len(self._execution_history),
            fallback_rate=round(self.get_fallback_rate() * 100, 1),
            avg_latency_ms=round(self.get_average_latency(), 1),
            avg_cost=round(self.get_average_cost(), 6),
        )

        if report.fallback_rate > 10:
            report.recommendations.append(f"High fallback rate ({report.fallback_rate}%) — check primary model availability")
        if report.avg_latency_ms > 3000:
            report.recommendations.append(f"High average latency ({report.avg_latency_ms}ms) — consider faster models")
        if report.avg_cost > 0.05:
            report.recommendations.append(f"Average cost per call ${report.avg_cost:.4f} — review model selection criteria")
        if not self._execution_history:
            report.recommendations.append("No execution history available yet")

        return report
