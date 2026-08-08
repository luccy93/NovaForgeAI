"""Agent Research — compare single, multi, parallel, hierarchical agents; planner strategies, reasoning chains, task routing, coordination, recovery, execution quality, completion time, resource usage."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


@dataclass
class AgentArchitectureEval:
    id: str
    architecture: str
    planner: str = ""
    agents_count: int = 1
    execution_quality: float = 0.0
    completion_time_ms: float = 0.0
    success_rate: float = 0.0
    resource_usage: dict = field(default_factory=dict)
    tasks_completed: int = 0
    total_tasks: int = 0
    cost: float = 0.0
    passed: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "AgentArchitectureEval": return cls(**data)


@dataclass
class CoordinationEval:
    strategy: str
    avg_quality: float
    avg_time_ms: float
    success_rate: float
    runs: int

    def to_dict(self) -> dict: return asdict(self)


class AgentResearch:
    def __init__(self, storage_dir: str = "research_data/agent_research"):
        self.storage_dir = storage_dir
        self._evals: dict[str, AgentArchitectureEval] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _store_path(self) -> str: return os.path.join(self.storage_dir, "evals.json")

    def _load(self) -> None:
        path = self._store_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    try: self._evals[k] = AgentArchitectureEval.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Failed to load agent research: %s", e)

    def _save(self) -> None:
        try:
            with open(self._store_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._evals.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save agent research: %s", e)

    def record_evaluation(self, architecture: str, planner: str, agents_count: int, execution_quality: float, completion_time_ms: float, success_rate: float, tasks_completed: int, total_tasks: int, cost: float = 0.0, resource_usage: dict = None) -> AgentArchitectureEval:
        eval = AgentArchitectureEval(
            id=str(uuid.uuid4()), architecture=architecture, planner=planner,
            agents_count=agents_count, execution_quality=execution_quality,
            completion_time_ms=completion_time_ms, success_rate=success_rate,
            resource_usage=resource_usage or {},
            tasks_completed=tasks_completed, total_tasks=total_tasks, cost=cost,
            passed=success_rate >= 0.8,
        )
        self._evals[eval.id] = eval
        self._save()
        return eval

    def compare_architectures(self) -> list[CoordinationEval]:
        by_arch = {}
        for e in self._evals.values():
            if e.architecture not in by_arch: by_arch[e.architecture] = []
            by_arch[e.architecture].append(e)
        return [CoordinationEval(
            strategy=arch,
            avg_quality=round(sum(e.execution_quality for e in evals) / len(evals), 4),
            avg_time_ms=round(sum(e.completion_time_ms for e in evals) / len(evals), 2),
            success_rate=round(sum(e.success_rate for e in evals) / len(evals), 4),
            runs=len(evals),
        ) for arch, evals in by_arch.items()]

    def compare_planners(self) -> list[CoordinationEval]:
        by_planner = {}
        for e in self._evals.values():
            if e.planner not in by_planner: by_planner[e.planner] = []
            by_planner[e.planner].append(e)
        return [CoordinationEval(
            strategy=planner,
            avg_quality=round(sum(e.execution_quality for e in evals) / len(evals), 4),
            avg_time_ms=round(sum(e.completion_time_ms for e in evals) / len(evals), 2),
            success_rate=round(sum(e.success_rate for e in evals) / len(evals), 4),
            runs=len(evals),
        ) for planner, evals in by_planner.items()]

    def get_leaderboard(self, top_n: int = 10) -> list[dict]:
        sorted_evals = sorted(self._evals.values(), key=lambda e: e.execution_quality, reverse=True)
        return [{"rank": i+1, "architecture": e.architecture, "planner": e.planner, "quality": e.execution_quality, "success_rate": e.success_rate, "time_ms": e.completion_time_ms, "agents": e.agents_count} for i, e in enumerate(sorted_evals[:top_n])]

    def get_telemetry(self) -> dict: return dict(self._telemetry)
