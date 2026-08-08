"""AI Reasoning Lab — research chain of thought, tree of thoughts, graph of thoughts, self-reflection, self-verification, debate, critic models, consensus models, reasoning trees, multi-step planning."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional, Any
from enum import Enum

logger = logging.getLogger(__name__)


class ReasoningStrategy(Enum):
    CHAIN_OF_THOUGHT = "chain_of_thought"
    TREE_OF_THOUGHTS = "tree_of_thoughts"
    GRAPH_OF_THOUGHTS = "graph_of_thoughts"
    SELF_REFLECTION = "self_reflection"
    SELF_VERIFICATION = "self_verification"
    DEBATE = "debate"
    CRITIC = "critic"
    CONSENSUS = "consensus"
    REASONING_TREE = "reasoning_tree"
    MULTI_STEP_PLANNING = "multi_step_planning"


@dataclass
class ReasoningStep:
    id: str
    content: str
    parent_id: Optional[str] = None
    score: float = 0.0
    children: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)


@dataclass
class ReasoningTrace:
    id: str
    strategy: ReasoningStrategy
    prompt: str = ""
    steps: list = field(default_factory=list)
    final_answer: str = ""
    score: float = 0.0
    steps_count: int = 0
    duration_ms: float = 0.0
    tokens_used: int = 0
    passed: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["strategy"] = self.strategy.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ReasoningTrace":
        data = data.copy()
        data["strategy"] = ReasoningStrategy(data.get("strategy", "chain_of_thought"))
        return cls(**data)


@dataclass
class StrategyComparison:
    strategy: str
    avg_score: float
    avg_steps: float
    avg_duration_ms: float
    success_rate: float
    runs: int

    def to_dict(self) -> dict: return asdict(self)


class ReasoningLab:
    def __init__(self, storage_dir: str = "research_data/reasoning"):
        self.storage_dir = storage_dir
        self._traces: dict[str, ReasoningTrace] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _store_path(self) -> str: return os.path.join(self.storage_dir, "traces.json")

    def _load(self) -> None:
        path = self._store_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    try: self._traces[k] = ReasoningTrace.from_dict(v)
                    except Exception as e: logger.warning("Skipping trace %s: %s", k, e)
            except Exception as e: logger.error("Failed to load reasoning lab: %s", e)

    def _save(self) -> None:
        try:
            with open(self._store_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._traces.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save reasoning lab: %s", e)

    def create_trace(self, prompt: str, strategy: ReasoningStrategy = ReasoningStrategy.CHAIN_OF_THOUGHT) -> ReasoningTrace:
        trace = ReasoningTrace(id=str(uuid.uuid4()), strategy=strategy, prompt=prompt)
        self._traces[trace.id] = trace
        self._save()
        return trace

    def add_step(self, trace_id: str, content: str, parent_id: str = "", score: float = 0.0, metadata: dict = None) -> Optional[ReasoningStep]:
        trace = self._traces.get(trace_id)
        if not trace: return None
        step = ReasoningStep(id=str(uuid.uuid4()), content=content, parent_id=parent_id or None, score=score, metadata=metadata or {})
        trace.steps.append(step)
        trace.steps_count = len(trace.steps)
        self._save()
        return step

    def complete_trace(self, trace_id: str, final_answer: str, score: float, duration_ms: float = 0.0, tokens_used: int = 0) -> Optional[ReasoningTrace]:
        trace = self._traces.get(trace_id)
        if not trace: return None
        trace.final_answer = final_answer
        trace.score = score
        trace.duration_ms = duration_ms
        trace.tokens_used = tokens_used
        trace.passed = score >= 0.7
        self._save()
        return trace

    def get_trace(self, trace_id: str) -> Optional[ReasoningTrace]: return self._traces.get(trace_id)

    def compare_strategies(self) -> list[StrategyComparison]:
        by_strategy = {}
        for t in self._traces.values():
            if t.strategy.value not in by_strategy: by_strategy[t.strategy.value] = []
            by_strategy[t.strategy.value].append(t)
        return [StrategyComparison(
            strategy=s,
            avg_score=round(sum(t.score for t in traces) / len(traces), 4),
            avg_steps=round(sum(t.steps_count for t in traces) / len(traces), 2),
            avg_duration_ms=round(sum(t.duration_ms for t in traces) / len(traces), 2),
            success_rate=round(sum(1 for t in traces if t.passed) / len(traces), 4),
            runs=len(traces),
        ) for s, traces in by_strategy.items()]

    def get_best_strategy(self) -> Optional[StrategyComparison]:
        comparisons = self.compare_strategies()
        return max(comparisons, key=lambda c: c.avg_score) if comparisons else None

    def list_traces(self, strategy: Optional[ReasoningStrategy] = None, limit: int = 50) -> list[ReasoningTrace]:
        results = list(self._traces.values())
        if strategy: results = [t for t in results if t.strategy == strategy]
        return sorted(results, key=lambda t: t.created_at, reverse=True)[:limit]

    def get_telemetry(self) -> dict: return dict(self._telemetry)
