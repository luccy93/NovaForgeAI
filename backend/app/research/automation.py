"""Research Automation — nightly benchmarks, weekly AI reports, monthly research reports, quarterly innovation reports, model health reports, prompt optimization reports, agent performance reports."""
import json, uuid, os, logging
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class AutomationFrequency(Enum):
    NIGHTLY = "nightly"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ON_DEMAND = "on_demand"


class AutomationType(Enum):
    BENCHMARK = "benchmark"
    REPORT = "report"
    EVALUATION = "evaluation"
    COMPARISON = "comparison"
    ANALYSIS = "analysis"
    OPTIMIZATION = "optimization"


@dataclass
class AutomationSchedule:
    id: str
    name: str
    automation_type: AutomationType
    frequency: AutomationFrequency
    config: dict = field(default_factory=dict)
    enabled: bool = True
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    total_runs: int = 0
    successful_runs: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["automation_type"] = self.automation_type.value
        d["frequency"] = self.frequency.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AutomationSchedule":
        data = data.copy()
        data["automation_type"] = AutomationType(data.get("automation_type", "benchmark"))
        data["frequency"] = AutomationFrequency(data.get("frequency", "nightly"))
        return cls(**data)


@dataclass
class AutomationRun:
    id: str
    schedule_id: str
    automation_type: AutomationType
    status: str = "running"
    output: dict = field(default_factory=dict)
    error: str = ""
    duration_ms: float = 0.0
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["automation_type"] = self.automation_type.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AutomationRun":
        data = data.copy()
        data["automation_type"] = AutomationType(data.get("automation_type", "benchmark"))
        return cls(**data)


class ResearchAutomation:
    def __init__(self, storage_dir: str = "research_data/automation"):
        self.storage_dir = storage_dir
        self._schedules: dict[str, AutomationSchedule] = {}
        self._runs: dict[str, AutomationRun] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _schedules_path(self) -> str: return os.path.join(self.storage_dir, "schedules.json")
    def _runs_path(self) -> str: return os.path.join(self.storage_dir, "runs.json")

    def _load(self) -> None:
        for path, store, cls in [
            (self._schedules_path(), self._schedules, AutomationSchedule),
            (self._runs_path(), self._runs, AutomationRun),
        ]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = cls.from_dict(v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Failed to load automation: %s", e)

    def _save(self) -> None:
        try:
            with open(self._schedules_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._schedules.items()}, f, indent=2, default=str)
            with open(self._runs_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._runs.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save automation: %s", e)

    def create_schedule(self, name: str, automation_type: AutomationType, frequency: AutomationFrequency, config: dict = None) -> AutomationSchedule:
        sched = AutomationSchedule(id=str(uuid.uuid4()), name=name, automation_type=automation_type, frequency=frequency, config=config or {})
        self._schedules[sched.id] = sched
        self._save()
        return sched

    def get_schedule(self, sched_id: str) -> Optional[AutomationSchedule]: return self._schedules.get(sched_id)

    def update_schedule(self, sched_id: str, updates: dict) -> Optional[AutomationSchedule]:
        sched = self._schedules.get(sched_id)
        if not sched: return None
        for k, v in updates.items():
            if hasattr(sched, k) and k not in ("id", "created_at"):
                if k == "automation_type": setattr(sched, k, AutomationType(v) if isinstance(v, str) else v)
                elif k == "frequency": setattr(sched, k, AutomationFrequency(v) if isinstance(v, str) else v)
                else: setattr(sched, k, v)
        sched.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return sched

    def record_run(self, schedule_id: str, automation_type: AutomationType, status: str = "completed", output: dict = None, error: str = "", duration_ms: float = 0.0) -> AutomationRun:
        run = AutomationRun(id=str(uuid.uuid4()), schedule_id=schedule_id, automation_type=automation_type, status=status, output=output or {}, error=error, duration_ms=duration_ms, completed_at=datetime.now(timezone.utc).isoformat())
        self._runs[run.id] = run
        sched = self._schedules.get(schedule_id)
        if sched:
            sched.last_run = run.completed_at
            sched.total_runs += 1
            if status == "completed": sched.successful_runs += 1
            sched.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return run

    def get_runs(self, schedule_id: str = "", limit: int = 50) -> list[AutomationRun]:
        results = list(self._runs.values())
        if schedule_id: results = [r for r in results if r.schedule_id == schedule_id]
        return sorted(results, key=lambda r: r.started_at, reverse=True)[:limit]

    def list_schedules(self, automation_type: Optional[AutomationType] = None) -> list[AutomationSchedule]:
        results = list(self._schedules.values())
        if automation_type: results = [s for s in results if s.automation_type == automation_type]
        return results

    def get_telemetry(self) -> dict: return dict(self._telemetry)
