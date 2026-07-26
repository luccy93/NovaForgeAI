"""Pipeline Manager — pipeline orchestration, stages, execution, retry, webhooks."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)

class PipelineStatus(Enum):
    PENDING = "pending"; RUNNING = "running"; SUCCEEDED = "succeeded"
    FAILED = "failed"; CANCELLED = "cancelled"; SKIPPED = "skipped"

@dataclass
class Pipeline:
    id: str; org_id: str; name: str; repository_id: str = ""
    status: PipelineStatus = PipelineStatus.PENDING
    stages: list = field(default_factory=list); triggers: list = field(default_factory=list)
    current_stage: str = ""; started_at: str = ""; completed_at: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self); d["status"] = self.status.value; return d

    @classmethod
    def from_dict(cls, data: dict) -> "Pipeline":
        data = data.copy(); data["status"] = PipelineStatus(data.get("status", "pending"))
        return cls(**data)

@dataclass
class PipelineStage:
    id: str; pipeline_id: str; name: str; order: int = 0
    status: PipelineStatus = PipelineStatus.PENDING
    commands: list = field(default_factory=list); env: dict = field(default_factory=dict)
    timeout_minutes: int = 60; retry_count: int = 0; max_retries: int = 2
    started_at: str = ""; completed_at: str = ""

    def to_dict(self) -> dict:
        d = asdict(self); d["status"] = self.status.value; return d

    @classmethod
    def from_dict(cls, data: dict) -> "PipelineStage":
        data = data.copy(); data["status"] = PipelineStatus(data.get("status", "pending"))
        return cls(**data)

class PipelineManager:
    def __init__(self, storage_dir: str = "release_data/pipelines"):
        self.storage_dir = storage_dir; self._pipelines: dict[str, Pipeline] = {}
        self._stages: dict[str, PipelineStage] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _pipe_path(self) -> str: return os.path.join(self.storage_dir, "pipelines.json")
    def _stage_path(self) -> str: return os.path.join(self.storage_dir, "stages.json")

    def _load(self) -> None:
        for path, store, cls in [(self._pipe_path(), self._pipelines, Pipeline), (self._stage_path(), self._stages, PipelineStage)]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f: data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = cls.from_dict(v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._pipe_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._pipelines.items()}, f, indent=2, default=str)
            with open(self._stage_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._stages.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def create(self, org_id: str, name: str, repository_id: str = "") -> Pipeline:
        p = Pipeline(id=str(uuid.uuid4()), org_id=org_id, name=name, repository_id=repository_id)
        self._pipelines[p.id] = p; self._save(); return p

    def add_stage(self, pipeline_id: str, name: str, order: int, commands: list = None, timeout: int = 60) -> Optional[PipelineStage]:
        if pipeline_id not in self._pipelines: return None
        s = PipelineStage(id=str(uuid.uuid4()), pipeline_id=pipeline_id, name=name, order=order, commands=commands or [], timeout_minutes=timeout)
        self._stages[s.id] = s
        pipe = self._pipelines[pipeline_id]
        if s.id not in pipe.stages: pipe.stages.append(s.id)
        self._save(); return s

    def update_status(self, pipe_id: str, status: PipelineStatus) -> Optional[Pipeline]:
        p = self._pipelines.get(pipe_id)
        if not p: return None
        p.status = status
        if status == PipelineStatus.RUNNING and not p.started_at: p.started_at = datetime.now(timezone.utc).isoformat()
        if status in (PipelineStatus.SUCCEEDED, PipelineStatus.FAILED, PipelineStatus.CANCELLED): p.completed_at = datetime.now(timezone.utc).isoformat()
        self._save(); return p

    def get_telemetry(self) -> dict: return dict(self._telemetry)
