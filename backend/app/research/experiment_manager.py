"""Experiment Manager — design, execute, track AI experiments."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional, Any
from enum import Enum

logger = logging.getLogger(__name__)


class ExperimentStatus(Enum):
    DRAFT = "draft"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ROLLED_BACK = "rolled_back"


class ExperimentType(Enum):
    A_B_TEST = "a_b_test"
    CANARY = "canary"
    SHADOW = "shadow"
    OFFLINE = "offline"
    REPLAY = "replay"
    SIMULATION = "simulation"
    BENCHMARK = "benchmark"
    AUTOMATED = "automated"


@dataclass
class ExperimentMetric:
    name: str
    value: float
    unit: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    tags: dict = field(default_factory=dict)

    def to_dict(self) -> dict: return asdict(self)


@dataclass
class ExperimentVariant:
    id: str
    name: str
    config: dict = field(default_factory=dict)
    metrics: list = field(default_factory=list)
    status: str = "pending"

    def to_dict(self) -> dict: return asdict(self)


@dataclass
class ExperimentHypothesis:
    statement: str
    expected_outcome: str
    metrics: list = field(default_factory=list)
    validated: Optional[bool] = None

    def to_dict(self) -> dict: return asdict(self)


@dataclass
class Experiment:
    id: str
    org_id: str
    name: str
    description: str = ""
    experiment_type: ExperimentType = ExperimentType.A_B_TEST
    status: ExperimentStatus = ExperimentStatus.DRAFT
    hypothesis: Optional[dict] = None
    variants: list = field(default_factory=list)
    metrics: list = field(default_factory=list)
    dataset_id: str = ""
    config: dict = field(default_factory=dict)
    tags: list = field(default_factory=list)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["experiment_type"] = self.experiment_type.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Experiment":
        data = data.copy()
        data["experiment_type"] = ExperimentType(data.get("experiment_type", "a_b_test"))
        data["status"] = ExperimentStatus(data.get("status", "draft"))
        return cls(**data)


class ExperimentManager:
    def __init__(self, storage_dir: str = "research_data/experiments"):
        self.storage_dir = storage_dir
        self._experiments: dict[str, Experiment] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _store_path(self) -> str: return os.path.join(self.storage_dir, "experiments.json")

    def _load(self) -> None:
        path = self._store_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    try: self._experiments[k] = Experiment.from_dict(v)
                    except Exception as e: logger.warning("Skipping experiment %s: %s", k, e)
            except Exception as e: logger.error("Failed to load experiments: %s", e)

    def _save(self) -> None:
        try:
            with open(self._store_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._experiments.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save experiments: %s", e)

    def create_experiment(self, name: str, org_id: str, exp_type: ExperimentType = ExperimentType.A_B_TEST, description: str = "") -> Experiment:
        exp = Experiment(id=str(uuid.uuid4()), org_id=org_id, name=name, description=description, experiment_type=exp_type)
        self._experiments[exp.id] = exp
        self._save()
        return exp

    def get_experiment(self, exp_id: str) -> Optional[Experiment]: return self._experiments.get(exp_id)

    def update_experiment(self, exp_id: str, updates: dict) -> Optional[Experiment]:
        exp = self._experiments.get(exp_id)
        if not exp: return None
        for k, v in updates.items():
            if hasattr(exp, k) and k not in ("id", "created_at"):
                if k == "experiment_type": setattr(exp, k, ExperimentType(v) if isinstance(v, str) else v)
                elif k == "status":
                    setattr(exp, k, ExperimentStatus(v) if isinstance(v, str) else v)
                    if exp.status == ExperimentStatus.RUNNING and not exp.started_at: exp.started_at = datetime.now(timezone.utc).isoformat()
                    if exp.status == ExperimentStatus.COMPLETED: exp.completed_at = datetime.now(timezone.utc).isoformat()
                else: setattr(exp, k, v)
        exp.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return exp

    def add_variant(self, exp_id: str, name: str, config: dict) -> Optional[ExperimentVariant]:
        exp = self._experiments.get(exp_id)
        if not exp: return None
        variant = ExperimentVariant(id=str(uuid.uuid4()), name=name, config=config)
        exp.variants.append(variant)
        exp.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return variant

    def add_metric(self, exp_id: str, name: str, value: float, unit: str = "", tags: dict = None) -> Optional[ExperimentMetric]:
        exp = self._experiments.get(exp_id)
        if not exp: return None
        metric = ExperimentMetric(name=name, value=value, unit=unit, tags=tags or {})
        exp.metrics.append(metric)
        exp.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return metric

    def set_hypothesis(self, exp_id: str, statement: str, expected_outcome: str, metrics: list = None) -> Optional[Experiment]:
        exp = self._experiments.get(exp_id)
        if not exp: return None
        exp.hypothesis = ExperimentHypothesis(statement=statement, expected_outcome=expected_outcome, metrics=metrics or []).to_dict()
        self._save()
        return exp

    def list_experiments(self, org_id: str = "", exp_type: Optional[ExperimentType] = None, status: Optional[ExperimentStatus] = None) -> list[Experiment]:
        results = []
        for exp in self._experiments.values():
            if org_id and exp.org_id != org_id: continue
            if exp_type and exp.experiment_type != exp_type: continue
            if status and exp.status != status: continue
            results.append(exp)
        return results

    def delete_experiment(self, exp_id: str) -> bool:
        if exp_id not in self._experiments: return False
        del self._experiments[exp_id]
        self._save()
        return True

    def get_telemetry(self) -> dict: return dict(self._telemetry)
