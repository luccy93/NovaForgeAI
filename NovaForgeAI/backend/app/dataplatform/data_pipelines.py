"""Data Pipelines — pipelines, steps, executions, metrics, and alerts for the Data Platform & Knowledge Fabric."""

import json
import uuid
import os
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


class PipelineMode(Enum):
    STREAMING = "streaming"
    BATCH = "batch"
    INCREMENTAL = "incremental"
    REAL_TIME = "real_time"
    EVENT_DRIVEN = "event_driven"
    SCHEDULED = "scheduled"


class PipelineStatus(Enum):
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DEGRADED = "degraded"


class PipelineStepType(Enum):
    EXTRACT = "extract"
    TRANSFORM = "transform"
    LOAD = "load"
    VALIDATE = "validate"
    ENRICH = "enrich"
    FILTER = "filter"
    AGGREGATE = "aggregate"
    JOIN = "join"
    DEDUP = "dedup"
    MERGE = "merge"
    SPLIT = "split"
    CACHE = "cache"


class RetryStrategy(Enum):
    FIXED = "fixed"
    EXPONENTIAL_BACKOFF = "exponential_backoff"
    IMMEDIATE = "immediate"
    NONE = "none"


@dataclass
class Pipeline:
    id: str
    org_id: str
    name: str
    description: str = ""
    mode: PipelineMode = PipelineMode.BATCH
    status: PipelineStatus = PipelineStatus.CREATED
    source: str = ""
    destination: str = ""
    schedule_cron: str = ""
    max_retries: int = 3
    retry_strategy: RetryStrategy = RetryStrategy.FIXED
    timeout_seconds: int = 3600
    tags: list = field(default_factory=list)
    config: dict = field(default_factory=dict)
    created_by: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["mode"] = self.mode.value
        d["status"] = self.status.value
        d["retry_strategy"] = self.retry_strategy.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Pipeline":
        data = data.copy()
        data["mode"] = PipelineMode(data.get("mode", "batch"))
        data["status"] = PipelineStatus(data.get("status", "created"))
        data["retry_strategy"] = RetryStrategy(data.get("retry_strategy", "fixed"))
        return cls(**data)


@dataclass
class PipelineStep:
    id: str
    pipeline_id: str
    step_type: PipelineStepType
    name: str = ""
    config: dict = field(default_factory=dict)
    order: int = 0
    retry_count: int = 0
    timeout_seconds: int = 300
    input_schema: dict = field(default_factory=dict)
    output_schema: dict = field(default_factory=dict)
    enabled: bool = True

    def to_dict(self) -> dict:
        d = asdict(self)
        d["step_type"] = self.step_type.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "PipelineStep":
        data = data.copy()
        data["step_type"] = PipelineStepType(data.get("step_type", "extract"))
        return cls(**data)


@dataclass
class PipelineExecution:
    id: str
    pipeline_id: str
    org_id: str
    status: PipelineStatus = PipelineStatus.CREATED
    started_at: str = ""
    completed_at: str = ""
    records_in: int = 0
    records_out: int = 0
    records_failed: int = 0
    bytes_processed: int = 0
    error_message: str = ""
    triggered_by: str = "manual"
    run_id: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "PipelineExecution":
        data = data.copy()
        data["status"] = PipelineStatus(data.get("status", "created"))
        return cls(**data)


@dataclass
class PipelineMetrics:
    id: str
    execution_id: str
    throughput: float = 0.0
    latency_ms: float = 0.0
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    error_rate: float = 0.0
    checkpoint: str = ""
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PipelineMetrics":
        return cls(**data)


@dataclass
class PipelineAlert:
    id: str
    pipeline_id: str
    org_id: str
    severity: str = "info"
    message: str = ""
    metric: str = ""
    threshold: float = 0.0
    current_value: float = 0.0
    triggered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    acknowledged_at: str = ""
    resolved_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PipelineAlert":
        return cls(**data)


class PipelineManager:
    def __init__(self, storage_dir: str = "pipeline_data"):
        self.storage_dir = storage_dir
        self._pipelines: dict[str, Pipeline] = {}
        self._steps: dict[str, PipelineStep] = {}
        self._executions: dict[str, PipelineExecution] = {}
        self._metrics: dict[str, PipelineMetrics] = {}
        self._alerts: dict[str, PipelineAlert] = {}
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _pipelines_path(self) -> str:
        return os.path.join(self.storage_dir, "pipelines.json")

    def _steps_path(self) -> str:
        return os.path.join(self.storage_dir, "steps.json")

    def _executions_path(self) -> str:
        return os.path.join(self.storage_dir, "executions.json")

    def _metrics_path(self) -> str:
        return os.path.join(self.storage_dir, "metrics.json")

    def _alerts_path(self) -> str:
        return os.path.join(self.storage_dir, "alerts.json")

    def _save(self) -> None:
        try:
            pipelines_data = {pid: p.to_dict() for pid, p in self._pipelines.items()}
            with open(self._pipelines_path(), "w", encoding="utf-8") as f:
                json.dump(pipelines_data, f, indent=2, default=str)

            steps_data = {sid: s.to_dict() for sid, s in self._steps.items()}
            with open(self._steps_path(), "w", encoding="utf-8") as f:
                json.dump(steps_data, f, indent=2, default=str)

            executions_data = {eid: e.to_dict() for eid, e in self._executions.items()}
            with open(self._executions_path(), "w", encoding="utf-8") as f:
                json.dump(executions_data, f, indent=2, default=str)

            metrics_data = {mid: m.to_dict() for mid, m in self._metrics.items()}
            with open(self._metrics_path(), "w", encoding="utf-8") as f:
                json.dump(metrics_data, f, indent=2, default=str)

            alerts_data = {aid: a.to_dict() for aid, a in self._alerts.items()}
            with open(self._alerts_path(), "w", encoding="utf-8") as f:
                json.dump(alerts_data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save pipeline data: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._pipelines_path()):
                with open(self._pipelines_path(), "r", encoding="utf-8") as f:
                    pipelines_data = json.load(f)
                for pid, data in pipelines_data.items():
                    try:
                        self._pipelines[pid] = Pipeline.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed pipeline %s: %s", pid, e)

            if os.path.exists(self._steps_path()):
                with open(self._steps_path(), "r", encoding="utf-8") as f:
                    steps_data = json.load(f)
                for sid, data in steps_data.items():
                    try:
                        self._steps[sid] = PipelineStep.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed step %s: %s", sid, e)

            if os.path.exists(self._executions_path()):
                with open(self._executions_path(), "r", encoding="utf-8") as f:
                    executions_data = json.load(f)
                for eid, data in executions_data.items():
                    try:
                        self._executions[eid] = PipelineExecution.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed execution %s: %s", eid, e)

            if os.path.exists(self._metrics_path()):
                with open(self._metrics_path(), "r", encoding="utf-8") as f:
                    metrics_data = json.load(f)
                for mid, data in metrics_data.items():
                    try:
                        self._metrics[mid] = PipelineMetrics.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed metrics %s: %s", mid, e)

            if os.path.exists(self._alerts_path()):
                with open(self._alerts_path(), "r", encoding="utf-8") as f:
                    alerts_data = json.load(f)
                for aid, data in alerts_data.items():
                    try:
                        self._alerts[aid] = PipelineAlert.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed alert %s: %s", aid, e)
        except Exception as e:
            logger.error("Failed to load pipeline data: %s", e, exc_info=True)

    def create_pipeline(self, pipeline: Pipeline) -> Pipeline:
        self._telemetry["create_pipeline_calls"] += 1
        if not pipeline.id:
            pipeline.id = str(uuid.uuid4())
        if not pipeline.created_at:
            pipeline.created_at = datetime.now(timezone.utc).isoformat()
        if not pipeline.updated_at:
            pipeline.updated_at = pipeline.created_at
        self._pipelines[pipeline.id] = pipeline
        self._save()
        logger.info("Created pipeline %s: %s (mode=%s)", pipeline.id, pipeline.name, pipeline.mode.value)
        return pipeline

    def get_pipeline(self, pipeline_id: str) -> Optional[Pipeline]:
        self._telemetry["get_pipeline_calls"] += 1
        return self._pipelines.get(pipeline_id)

    def update_pipeline(self, pipeline_id: str, updates: dict) -> Optional[Pipeline]:
        self._telemetry["update_pipeline_calls"] += 1
        pipeline = self._pipelines.get(pipeline_id)
        if not pipeline:
            logger.warning("Attempted to update unknown pipeline: %s", pipeline_id)
            return None
        for key, value in updates.items():
            if hasattr(pipeline, key) and key not in ("id", "created_at"):
                if key == "mode":
                    setattr(pipeline, key, PipelineMode(value) if isinstance(value, str) else value)
                elif key == "status":
                    setattr(pipeline, key, PipelineStatus(value) if isinstance(value, str) else value)
                elif key == "retry_strategy":
                    setattr(pipeline, key, RetryStrategy(value) if isinstance(value, str) else value)
                else:
                    setattr(pipeline, key, value)
        pipeline.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        logger.info("Updated pipeline: %s", pipeline_id)
        return pipeline

    def list_pipelines(self, org_id: str, mode: Optional[PipelineMode] = None, status: Optional[PipelineStatus] = None) -> list[Pipeline]:
        self._telemetry["list_pipelines_calls"] += 1
        results = []
        for p in self._pipelines.values():
            if p.org_id != org_id:
                continue
            if mode and p.mode != mode:
                continue
            if status and p.status != status:
                continue
            results.append(p)
        return results

    def add_pipeline_step(self, step: PipelineStep) -> PipelineStep:
        self._telemetry["add_pipeline_step_calls"] += 1
        if not step.id:
            step.id = str(uuid.uuid4())
        self._steps[step.id] = step
        self._save()
        logger.info("Added step %s to pipeline %s: %s", step.id, step.pipeline_id, step.step_type.value)
        return step

    def list_pipeline_steps(self, pipeline_id: str) -> list[PipelineStep]:
        self._telemetry["list_pipeline_steps_calls"] += 1
        return sorted(
            [s for s in self._steps.values() if s.pipeline_id == pipeline_id],
            key=lambda s: s.order,
        )

    def execute_pipeline(self, pipeline_id: str, triggered_by: str = "manual") -> PipelineExecution:
        self._telemetry["execute_pipeline_calls"] += 1
        pipeline = self._pipelines.get(pipeline_id)
        if not pipeline:
            logger.warning("Attempted to execute unknown pipeline: %s", pipeline_id)
            execution = PipelineExecution(
                id=str(uuid.uuid4()),
                pipeline_id=pipeline_id,
                org_id="",
                status=PipelineStatus.FAILED,
                error_message="Pipeline not found",
                triggered_by=triggered_by,
                run_id=str(uuid.uuid4()),
            )
            self._executions[execution.id] = execution
            self._save()
            return execution

        execution = PipelineExecution(
            id=str(uuid.uuid4()),
            pipeline_id=pipeline_id,
            org_id=pipeline.org_id,
            status=PipelineStatus.RUNNING,
            started_at=datetime.now(timezone.utc).isoformat(),
            triggered_by=triggered_by,
            run_id=str(uuid.uuid4()),
        )

        pipeline.status = PipelineStatus.RUNNING
        pipeline.updated_at = datetime.now(timezone.utc).isoformat()
        self._executions[execution.id] = execution
        self._save()
        logger.info("Executed pipeline %s (run=%s, triggered_by=%s)", pipeline_id, execution.run_id, triggered_by)
        return execution

    def get_execution(self, execution_id: str) -> Optional[PipelineExecution]:
        self._telemetry["get_execution_calls"] += 1
        return self._executions.get(execution_id)

    def list_executions(self, pipeline_id: str, limit: int = 20) -> list[PipelineExecution]:
        self._telemetry["list_executions_calls"] += 1
        results = [e for e in self._executions.values() if e.pipeline_id == pipeline_id]
        results.sort(key=lambda e: e.started_at, reverse=True)
        return results[:limit]

    def record_metrics(self, metrics: PipelineMetrics) -> PipelineMetrics:
        self._telemetry["record_metrics_calls"] += 1
        if not metrics.id:
            metrics.id = str(uuid.uuid4())
        if not metrics.generated_at:
            metrics.generated_at = datetime.now(timezone.utc).isoformat()
        self._metrics[metrics.id] = metrics
        self._save()
        logger.info("Recorded pipeline metrics %s for execution %s", metrics.id, metrics.execution_id)
        return metrics

    def create_alert(self, alert: PipelineAlert) -> PipelineAlert:
        self._telemetry["create_alert_calls"] += 1
        if not alert.id:
            alert.id = str(uuid.uuid4())
        if not alert.triggered_at:
            alert.triggered_at = datetime.now(timezone.utc).isoformat()
        self._alerts[alert.id] = alert
        self._save()
        logger.info("Created pipeline alert %s for pipeline %s (severity=%s)", alert.id, alert.pipeline_id, alert.severity)
        return alert

    def get_pipeline_stats(self, org_id: str) -> dict:
        self._telemetry["get_pipeline_stats_calls"] += 1
        org_pipelines = [p for p in self._pipelines.values() if p.org_id == org_id]
        org_steps = [s for s in self._steps.values() if s.pipeline_id in {p.id for p in org_pipelines}]
        org_executions = [e for e in self._executions.values() if e.org_id == org_id]
        org_metrics_list = [m for m in self._metrics.values()
                           if m.execution_id in {e.id for e in org_executions}]
        org_alerts = [a for a in self._alerts.values() if a.org_id == org_id]

        by_mode: dict[str, int] = defaultdict(int)
        by_status: dict[str, int] = defaultdict(int)
        total_records_in = 0
        total_records_out = 0
        total_records_failed = 0
        total_bytes = 0

        for p in org_pipelines:
            by_mode[p.mode.value] += 1
            by_status[p.status.value] += 1

        for e in org_executions:
            total_records_in += e.records_in
            total_records_out += e.records_out
            total_records_failed += e.records_failed
            total_bytes += e.bytes_processed

        return {
            "org_id": org_id,
            "total_pipelines": len(org_pipelines),
            "total_steps": len(org_steps),
            "total_executions": len(org_executions),
            "total_metrics_records": len(org_metrics_list),
            "total_alerts": len(org_alerts),
            "total_records_in": total_records_in,
            "total_records_out": total_records_out,
            "total_records_failed": total_records_failed,
            "total_bytes_processed": total_bytes,
            "by_mode": dict(by_mode),
            "by_status": dict(by_status),
        }

    def get_telemetry(self) -> dict:
        self._telemetry["get_telemetry_calls"] += 1
        return dict(self._telemetry)