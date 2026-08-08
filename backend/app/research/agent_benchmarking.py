"""Agent Benchmarking — compare single, multi, parallel, hierarchical agents; evaluate planner strategies, reasoning chains, task routing, coordination, recovery, execution quality, completion time, resource usage."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class AgentArchitecture(Enum):
    SINGLE = "single"
    MULTI = "multi"
    PARALLEL = "parallel"
    HIERARCHICAL = "hierarchical"


class PlannerStrategy(Enum):
    REACT = "react"
    PLAN_EXECUTE = "plan_execute"
    TREE_OF_THOUGHTS = "tree_of_thoughts"
    CHAIN_OF_THOUGHT = "chain_of_thought"
    FUNCTION_CALLING = "function_calling"


@dataclass
class AgentBenchmarkConfig:
    architecture: AgentArchitecture = AgentArchitecture.SINGLE
    planner: PlannerStrategy = PlannerStrategy.REACT
    max_steps: int = 20
    num_agents: int = 1
    timeout_seconds: int = 300
    tools_available: list = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["architecture"] = self.architecture.value
        d["planner"] = self.planner.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AgentBenchmarkConfig":
        data = data.copy()
        data["architecture"] = AgentArchitecture(data.get("architecture", "single"))
        data["planner"] = PlannerStrategy(data.get("planner", "react"))
        return cls(**data)


@dataclass
class AgentTaskResult:
    task_id: str
    task_description: str
    completed: bool = False
    steps_taken: int = 0
    duration_ms: float = 0.0
    tokens_used: int = 0
    cost: float = 0.0
    errors: list = field(default_factory=list)
    output_quality: float = 0.0

    def to_dict(self) -> dict: return asdict(self)


@dataclass
class AgentBenchmarkResult:
    id: str
    config: dict
    task_results: list = field(default_factory=list)
    execution_quality: float = 0.0
    avg_completion_time_ms: float = 0.0
    resource_usage: dict = field(default_factory=dict)
    success_rate: float = 0.0
    total_cost: float = 0.0
    passed: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AgentBenchmarkResult":
        return cls(**data)


class AgentBenchmarking:
    def __init__(self, storage_dir: str = "research_data/agent_benchmarks"):
        self.storage_dir = storage_dir
        self._results: dict[str, AgentBenchmarkResult] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _store_path(self) -> str: return os.path.join(self.storage_dir, "results.json")

    def _load(self) -> None:
        path = self._store_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    try: self._results[k] = AgentBenchmarkResult.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Failed to load agent benchmarks: %s", e)

    def _save(self) -> None:
        try:
            with open(self._store_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._results.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save agent benchmarks: %s", e)

    def run_benchmark(self, config: AgentBenchmarkConfig, task_results: list[AgentTaskResult] = None) -> AgentBenchmarkResult:
        tr = task_results or []
        n = len(tr) or 1
        completed = sum(1 for t in tr if t.completed)
        quality = sum(t.output_quality for t in tr) / n
        avg_time = sum(t.duration_ms for t in tr) / n
        total_cost = sum(t.cost for t in tr)
        total_tokens = sum(t.tokens_used for t in tr)
        success_rate = completed / n
        result = AgentBenchmarkResult(
            id=str(uuid.uuid4()), config=config.to_dict(), task_results=[t.to_dict() for t in tr],
            execution_quality=round(quality, 4), avg_completion_time_ms=round(avg_time, 2),
            resource_usage={"total_tokens": total_tokens, "total_tasks": n, "completed": completed},
            success_rate=round(success_rate, 4), total_cost=round(total_cost, 6),
            passed=success_rate >= 0.8,
        )
        self._results[result.id] = result
        self._save()
        return result

    def compare_architectures(self) -> dict:
        by_arch = {}
        for r in self._results.values():
            arch = r.config.get("architecture", "unknown")
            if arch not in by_arch: by_arch[arch] = []
            by_arch[arch].append(r)
        comparison = {}
        for arch, results in by_arch.items():
            n = len(results)
            comparison[arch] = {
                "avg_execution_quality": round(sum(r.execution_quality for r in results) / n, 4),
                "avg_completion_time_ms": round(sum(r.avg_completion_time_ms for r in results) / n, 2),
                "avg_success_rate": round(sum(r.success_rate for r in results) / n, 4),
                "avg_cost": round(sum(r.total_cost for r in results) / n, 6),
                "count": n,
            }
        return comparison

    def compare_planners(self) -> dict:
        by_planner = {}
        for r in self._results.values():
            planner = r.config.get("planner", "unknown")
            if planner not in by_planner: by_planner[planner] = []
            by_planner[planner].append(r)
        comparison = {}
        for planner, results in by_planner.items():
            n = len(results)
            comparison[planner] = {
                "avg_quality": round(sum(r.execution_quality for r in results) / n, 4),
                "avg_time_ms": round(sum(r.avg_completion_time_ms for r in results) / n, 2),
                "avg_success_rate": round(sum(r.success_rate for r in results) / n, 4),
                "count": n,
            }
        return comparison

    def get_leaderboard(self, metric: str = "execution_quality", top_n: int = 10) -> list[dict]:
        sorted_results = sorted(self._results.values(), key=lambda r: getattr(r, metric, 0.0), reverse=True)
        return [{"rank": i+1, "id": r.id, "config": r.config, metric: getattr(r, metric, 0.0), "success_rate": r.success_rate, "avg_time_ms": r.avg_completion_time_ms} for i, r in enumerate(sorted_results[:top_n])]

    def list_results(self, limit: int = 50) -> list[AgentBenchmarkResult]:
        results = sorted(self._results.values(), key=lambda r: r.created_at, reverse=True)
        return results[:limit]

    def get_telemetry(self) -> dict: return dict(self._telemetry)
