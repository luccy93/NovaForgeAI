"""Autonomous Experiments — A/B testing, canary AI, shadow mode, offline evaluation, replay evaluation, simulation, benchmark runs, automated experiments."""
import json, uuid, os, logging
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field, asdict
from typing import Optional, Any
from enum import Enum

logger = logging.getLogger(__name__)


class ExperimentRunMode(Enum):
    A_B_TEST = "a_b_test"
    CANARY = "canary"
    SHADOW = "shadow"
    OFFLINE = "offline"
    REPLAY = "replay"
    SIMULATION = "simulation"
    BENCHMARK = "benchmark"
    AUTOMATED = "automated"


class ExperimentRunStatus(Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class ExperimentRun:
    id: str
    org_id: str
    name: str
    mode: ExperimentRunMode
    status: ExperimentRunStatus = ExperimentRunStatus.QUEUED
    config: dict = field(default_factory=dict)
    control_config: dict = field(default_factory=dict)
    treatment_config: dict = field(default_factory=dict)
    results: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)
    traffic_percentage: float = 50.0
    duration_minutes: int = 60
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["mode"] = self.mode.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ExperimentRun":
        data = data.copy()
        data["mode"] = ExperimentRunMode(data.get("mode", "automated"))
        data["status"] = ExperimentRunStatus(data.get("status", "queued"))
        return cls(**data)


@dataclass
class AutonomousExperimentConfig:
    enabled: bool = True
    schedule_interval_hours: int = 24
    max_concurrent: int = 3
    auto_rollback: bool = True
    notify_on_completion: bool = True
    evaluation_criteria: dict = field(default_factory=lambda: {"min_success_rate": 0.8, "max_latency_pct_increase": 20})
    preferred_modes: list = field(default_factory=lambda: ["shadow", "a_b_test", "canary"])

    def to_dict(self) -> dict: return asdict(self)


class AutonomousExperiments:
    def __init__(self, storage_dir: str = "research_data/auto_experiments"):
        self.storage_dir = storage_dir
        self._runs: dict[str, ExperimentRun] = {}
        self._config: AutonomousExperimentConfig = AutonomousExperimentConfig()
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _runs_path(self) -> str: return os.path.join(self.storage_dir, "runs.json")
    def _config_path(self) -> str: return os.path.join(self.storage_dir, "config.json")

    def _load(self) -> None:
        for path, store, cls in [
            (self._runs_path(), self._runs, ExperimentRun),
            (self._config_path(), None, None),
        ]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if cls:
                        for k, v in data.items():
                            try: store[k] = cls.from_dict(v)
                            except Exception as e: logger.warning("Skipping %s: %s", k, e)
                    else:
                        self._config = AutonomousExperimentConfig(**data)
                except Exception as e: logger.error("Failed to load auto experiments: %s", e)

    def _save(self) -> None:
        try:
            with open(self._runs_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._runs.items()}, f, indent=2, default=str)
            with open(self._config_path(), "w", encoding="utf-8") as f:
                json.dump(self._config.to_dict(), f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save auto experiments: %s", e)

    def schedule_run(self, name: str, org_id: str, mode: ExperimentRunMode, config: dict = None, control_config: dict = None, treatment_config: dict = None, traffic_percentage: float = 50.0, duration_minutes: int = 60) -> ExperimentRun:
        run = ExperimentRun(
            id=str(uuid.uuid4()), org_id=org_id, name=name, mode=mode,
            config=config or {}, control_config=control_config or {},
            treatment_config=treatment_config or {},
            traffic_percentage=traffic_percentage, duration_minutes=duration_minutes,
        )
        self._runs[run.id] = run
        self._save()
        return run

    def start_run(self, run_id: str) -> Optional[ExperimentRun]:
        run = self._runs.get(run_id)
        if not run: return None
        run.status = ExperimentRunStatus.RUNNING
        run.started_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return run

    def complete_run(self, run_id: str, results: dict, metrics: dict) -> Optional[ExperimentRun]:
        run = self._runs.get(run_id)
        if not run: return None
        run.status = ExperimentRunStatus.COMPLETED
        run.completed_at = datetime.now(timezone.utc).isoformat()
        run.results = results
        run.metrics = metrics
        self._save()
        return run

    def rollback_run(self, run_id: str, reason: str = "") -> Optional[ExperimentRun]:
        run = self._runs.get(run_id)
        if not run: return None
        run.status = ExperimentRunStatus.ROLLED_BACK
        run.completed_at = datetime.now(timezone.utc).isoformat()
        run.results["rollback_reason"] = reason
        self._save()
        return run

    def get_run(self, run_id: str) -> Optional[ExperimentRun]: return self._runs.get(run_id)

    def list_runs(self, org_id: str = "", mode: Optional[ExperimentRunMode] = None, status: Optional[ExperimentRunStatus] = None) -> list[ExperimentRun]:
        results = list(self._runs.values())
        if org_id: results = [r for r in results if r.org_id == org_id]
        if mode: results = [r for r in results if r.mode == mode]
        if status: results = [r for r in results if r.status == status]
        return sorted(results, key=lambda r: r.created_at, reverse=True)

    def update_config(self, updates: dict) -> AutonomousExperimentConfig:
        for k, v in updates.items():
            if hasattr(self._config, k):
                setattr(self._config, k, v)
        self._save()
        return self._config

    def get_config(self) -> AutonomousExperimentConfig: return self._config

    def get_telemetry(self) -> dict: return dict(self._telemetry)
