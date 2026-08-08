"""Data Ingestion — connectors, jobs, batches, mappings, and metrics for the Data Platform & Knowledge Fabric."""

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


class IngestionSourceType(Enum):
    GITHUB = "github"
    GITLAB = "gitlab"
    BITBUCKET = "bitbucket"
    JIRA = "jira"
    LINEAR = "linear"
    SLACK = "slack"
    NOTION = "notion"
    CONFLUENCE = "confluence"
    GOOGLE_DRIVE = "google_drive"
    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"
    DOCKER = "docker"
    KUBERNETES = "kubernetes"
    REST_API = "rest_api"
    FILE_UPLOAD = "file_upload"
    MANUAL = "manual"
    WEBHOOK = "webhook"


class IngestionStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class IngestionMode(Enum):
    FULL = "full"
    INCREMENTAL = "incremental"
    DELTA = "delta"
    SNAPSHOT = "snapshot"
    CDC = "cdc"


class IngestionSchedule(Enum):
    ON_DEMAND = "on_demand"
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    CRON = "cron"


class IngestionFormat(Enum):
    JSON = "json"
    CSV = "csv"
    PARQUET = "parquet"
    AVRO = "avro"
    PROTOBUF = "protobuf"
    XML = "xml"
    YAML = "yaml"
    MARKDOWN = "markdown"
    BINARY = "binary"


@dataclass
class IngestionConnector:
    id: str
    org_id: str
    name: str
    source_type: IngestionSourceType
    config: dict = field(default_factory=dict)
    credentials_ref: str = ""
    enabled: bool = True
    health_status: str = "unknown"
    last_connected: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["source_type"] = self.source_type.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "IngestionConnector":
        data = data.copy()
        data["source_type"] = IngestionSourceType(data.get("source_type", "manual"))
        return cls(**data)


@dataclass
class IngestionJob:
    id: str
    org_id: str
    connector_id: str
    source_type: IngestionSourceType
    mode: IngestionMode
    status: IngestionStatus = IngestionStatus.PENDING
    schedule: IngestionSchedule = IngestionSchedule.ON_DEMAND
    config: dict = field(default_factory=dict)
    started_at: str = ""
    completed_at: str = ""
    records_processed: int = 0
    records_failed: int = 0
    error_message: str = ""
    created_by: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["source_type"] = self.source_type.value
        d["mode"] = self.mode.value
        d["status"] = self.status.value
        d["schedule"] = self.schedule.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "IngestionJob":
        data = data.copy()
        data["source_type"] = IngestionSourceType(data.get("source_type", "manual"))
        data["mode"] = IngestionMode(data.get("mode", "full"))
        data["status"] = IngestionStatus(data.get("status", "pending"))
        data["schedule"] = IngestionSchedule(data.get("schedule", "on_demand"))
        return cls(**data)


@dataclass
class IngestionBatch:
    id: str
    job_id: str
    org_id: str
    batch_number: int
    status: IngestionStatus = IngestionStatus.PENDING
    records_count: int = 0
    size_bytes: int = 0
    started_at: str = ""
    completed_at: str = ""
    error_message: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "IngestionBatch":
        data = data.copy()
        data["status"] = IngestionStatus(data.get("status", "pending"))
        return cls(**data)


@dataclass
class IngestionMapping:
    id: str
    org_id: str
    name: str
    source_type: IngestionSourceType
    field_mappings: list[dict] = field(default_factory=list)
    transformations: list[dict] = field(default_factory=list)
    validation_rules: list = field(default_factory=list)
    enabled: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["source_type"] = self.source_type.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "IngestionMapping":
        data = data.copy()
        data["source_type"] = IngestionSourceType(data.get("source_type", "manual"))
        return cls(**data)


@dataclass
class IngestionMetrics:
    id: str
    job_id: str
    org_id: str
    total_records: int = 0
    success_count: int = 0
    failure_count: int = 0
    processing_rate: float = 0.0
    avg_latency_ms: float = 0.0
    peak_memory_mb: float = 0.0
    storage_written_bytes: int = 0
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "IngestionMetrics":
        return cls(**data)


class IngestionManager:
    def __init__(self, storage_dir: str = "ingestion_data"):
        self.storage_dir = storage_dir
        self._connectors: dict[str, IngestionConnector] = {}
        self._jobs: dict[str, IngestionJob] = {}
        self._batches: dict[str, IngestionBatch] = {}
        self._mappings: dict[str, IngestionMapping] = {}
        self._metrics: dict[str, IngestionMetrics] = {}
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _connectors_path(self) -> str:
        return os.path.join(self.storage_dir, "connectors.json")

    def _jobs_path(self) -> str:
        return os.path.join(self.storage_dir, "jobs.json")

    def _batches_path(self) -> str:
        return os.path.join(self.storage_dir, "batches.json")

    def _mappings_path(self) -> str:
        return os.path.join(self.storage_dir, "mappings.json")

    def _metrics_path(self) -> str:
        return os.path.join(self.storage_dir, "metrics.json")

    def _save(self) -> None:
        try:
            conn_data = {cid: c.to_dict() for cid, c in self._connectors.items()}
            with open(self._connectors_path(), "w", encoding="utf-8") as f:
                json.dump(conn_data, f, indent=2, default=str)

            jobs_data = {jid: j.to_dict() for jid, j in self._jobs.items()}
            with open(self._jobs_path(), "w", encoding="utf-8") as f:
                json.dump(jobs_data, f, indent=2, default=str)

            batches_data = {bid: b.to_dict() for bid, b in self._batches.items()}
            with open(self._batches_path(), "w", encoding="utf-8") as f:
                json.dump(batches_data, f, indent=2, default=str)

            mappings_data = {mid: m.to_dict() for mid, m in self._mappings.items()}
            with open(self._mappings_path(), "w", encoding="utf-8") as f:
                json.dump(mappings_data, f, indent=2, default=str)

            metrics_data = {mid: m.to_dict() for mid, m in self._metrics.items()}
            with open(self._metrics_path(), "w", encoding="utf-8") as f:
                json.dump(metrics_data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save ingestion data: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._connectors_path()):
                with open(self._connectors_path(), "r", encoding="utf-8") as f:
                    conn_data = json.load(f)
                for cid, data in conn_data.items():
                    try:
                        self._connectors[cid] = IngestionConnector.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed connector %s: %s", cid, e)

            if os.path.exists(self._jobs_path()):
                with open(self._jobs_path(), "r", encoding="utf-8") as f:
                    jobs_data = json.load(f)
                for jid, data in jobs_data.items():
                    try:
                        self._jobs[jid] = IngestionJob.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed job %s: %s", jid, e)

            if os.path.exists(self._batches_path()):
                with open(self._batches_path(), "r", encoding="utf-8") as f:
                    batches_data = json.load(f)
                for bid, data in batches_data.items():
                    try:
                        self._batches[bid] = IngestionBatch.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed batch %s: %s", bid, e)

            if os.path.exists(self._mappings_path()):
                with open(self._mappings_path(), "r", encoding="utf-8") as f:
                    mappings_data = json.load(f)
                for mid, data in mappings_data.items():
                    try:
                        self._mappings[mid] = IngestionMapping.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed mapping %s: %s", mid, e)

            if os.path.exists(self._metrics_path()):
                with open(self._metrics_path(), "r", encoding="utf-8") as f:
                    metrics_data = json.load(f)
                for mid, data in metrics_data.items():
                    try:
                        self._metrics[mid] = IngestionMetrics.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed metrics %s: %s", mid, e)
        except Exception as e:
            logger.error("Failed to load ingestion data: %s", e, exc_info=True)

    def register_connector(self, connector: IngestionConnector) -> IngestionConnector:
        self._telemetry["register_connector_calls"] += 1
        if not connector.id:
            connector.id = str(uuid.uuid4())
        if not connector.created_at:
            connector.created_at = datetime.now(timezone.utc).isoformat()
        if not connector.updated_at:
            connector.updated_at = connector.created_at
        self._connectors[connector.id] = connector
        self._save()
        logger.info("Registered connector %s: %s (%s)", connector.id, connector.name, connector.source_type.value)
        return connector

    def get_connector(self, connector_id: str) -> Optional[IngestionConnector]:
        self._telemetry["get_connector_calls"] += 1
        return self._connectors.get(connector_id)

    def update_connector(self, connector_id: str, updates: dict) -> Optional[IngestionConnector]:
        self._telemetry["update_connector_calls"] += 1
        connector = self._connectors.get(connector_id)
        if not connector:
            logger.warning("Attempted to update unknown connector: %s", connector_id)
            return None
        for key, value in updates.items():
            if hasattr(connector, key) and key not in ("id", "created_at"):
                if key == "source_type":
                    setattr(connector, key, IngestionSourceType(value) if isinstance(value, str) else value)
                else:
                    setattr(connector, key, value)
        connector.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        logger.info("Updated connector: %s", connector_id)
        return connector

    def list_connectors(self, org_id: str, source_type: Optional[IngestionSourceType] = None) -> list[IngestionConnector]:
        self._telemetry["list_connectors_calls"] += 1
        results = []
        for conn in self._connectors.values():
            if conn.org_id != org_id:
                continue
            if source_type and conn.source_type != source_type:
                continue
            results.append(conn)
        return results

    def create_job(self, job: IngestionJob) -> IngestionJob:
        self._telemetry["create_job_calls"] += 1
        if not job.id:
            job.id = str(uuid.uuid4())
        if not job.created_at:
            job.created_at = datetime.now(timezone.utc).isoformat()
        if job.status == IngestionStatus.PENDING and not job.started_at:
            job.started_at = datetime.now(timezone.utc).isoformat()
            job.status = IngestionStatus.RUNNING
        self._jobs[job.id] = job
        self._save()
        logger.info("Created ingestion job %s: connector=%s mode=%s", job.id, job.connector_id, job.mode.value)
        return job

    def start_job(self, job_id: str) -> Optional[IngestionJob]:
        self._telemetry["start_job_calls"] += 1
        job = self._jobs.get(job_id)
        if not job:
            logger.warning("Attempted to start unknown job: %s", job_id)
            return None
        job.status = IngestionStatus.RUNNING
        job.started_at = datetime.now(timezone.utc).isoformat()
        self._save()
        logger.info("Started ingestion job: %s", job_id)
        return job

    def complete_job(self, job_id: str, status: IngestionStatus, records_processed: int, records_failed: int) -> Optional[IngestionJob]:
        self._telemetry["complete_job_calls"] += 1
        job = self._jobs.get(job_id)
        if not job:
            logger.warning("Attempted to complete unknown job: %s", job_id)
            return None
        job.status = status
        job.records_processed = records_processed
        job.records_failed = records_failed
        job.completed_at = datetime.now(timezone.utc).isoformat()
        self._save()
        logger.info("Completed ingestion job %s: status=%s processed=%d failed=%d", job_id, status.value, records_processed, records_failed)
        return job

    def fail_job(self, job_id: str, error: str) -> Optional[IngestionJob]:
        self._telemetry["fail_job_calls"] += 1
        job = self._jobs.get(job_id)
        if not job:
            logger.warning("Attempted to fail unknown job: %s", job_id)
            return None
        job.status = IngestionStatus.FAILED
        job.error_message = error
        job.completed_at = datetime.now(timezone.utc).isoformat()
        self._save()
        logger.error("Failed ingestion job %s: %s", job_id, error)
        return job

    def get_job(self, job_id: str) -> Optional[IngestionJob]:
        self._telemetry["get_job_calls"] += 1
        return self._jobs.get(job_id)

    def list_jobs(self, org_id: str, status: Optional[IngestionStatus] = None, source_type: Optional[IngestionSourceType] = None) -> list[IngestionJob]:
        self._telemetry["list_jobs_calls"] += 1
        results = []
        for job in self._jobs.values():
            if job.org_id != org_id:
                continue
            if status and job.status != status:
                continue
            if source_type and job.source_type != source_type:
                continue
            results.append(job)
        return results

    def create_batch(self, batch: IngestionBatch) -> IngestionBatch:
        self._telemetry["create_batch_calls"] += 1
        if not batch.id:
            batch.id = str(uuid.uuid4())
        if not batch.started_at:
            batch.started_at = datetime.now(timezone.utc).isoformat()
        if batch.status == IngestionStatus.PENDING:
            batch.status = IngestionStatus.RUNNING
        self._batches[batch.id] = batch
        self._save()
        logger.info("Created ingestion batch %s for job %s (batch #%d)", batch.id, batch.job_id, batch.batch_number)
        return batch

    def record_metrics(self, metrics: IngestionMetrics) -> IngestionMetrics:
        self._telemetry["record_metrics_calls"] += 1
        if not metrics.id:
            metrics.id = str(uuid.uuid4())
        if not metrics.generated_at:
            metrics.generated_at = datetime.now(timezone.utc).isoformat()
        self._metrics[metrics.id] = metrics
        self._save()
        logger.info("Recorded ingestion metrics %s for job %s", metrics.id, metrics.job_id)
        return metrics

    def create_mapping(self, mapping: IngestionMapping) -> IngestionMapping:
        self._telemetry["create_mapping_calls"] += 1
        if not mapping.id:
            mapping.id = str(uuid.uuid4())
        if not mapping.created_at:
            mapping.created_at = datetime.now(timezone.utc).isoformat()
        if not mapping.updated_at:
            mapping.updated_at = mapping.created_at
        self._mappings[mapping.id] = mapping
        self._save()
        logger.info("Created ingestion mapping %s: %s", mapping.id, mapping.name)
        return mapping

    def apply_mapping(self, mapping_id: str, record: dict) -> dict:
        self._telemetry["apply_mapping_calls"] += 1
        mapping = self._mappings.get(mapping_id)
        if not mapping:
            logger.warning("Attempted to apply unknown mapping: %s", mapping_id)
            return record

        result = {}
        for fm in mapping.field_mappings:
            source_field = fm.get("source_field", "")
            target_field = fm.get("target_field", "")
            default = fm.get("default", None)

            value = record
            for part in source_field.split("."):
                if isinstance(value, dict):
                    value = value.get(part)
                else:
                    value = None
                    break

            if value is None and default is not None:
                value = default

            target_parts = target_field.split(".")
            target = result
            for i, part in enumerate(target_parts):
                if i == len(target_parts) - 1:
                    target[part] = value
                else:
                    if part not in target:
                        target[part] = {}
                    target = target[part]

        for tf in mapping.transformations:
            field = tf.get("field", "")
            transform_type = tf.get("type", "")
            transform_config = tf.get("config", {})

            target_parts = field.split(".")
            target = result
            for i, part in enumerate(target_parts):
                if isinstance(target, dict) and part in target:
                    if i == len(target_parts) - 1:
                        val = target[part]
                        if transform_type == "upper" and isinstance(val, str):
                            target[part] = val.upper()
                        elif transform_type == "lower" and isinstance(val, str):
                            target[part] = val.lower()
                        elif transform_type == "strip" and isinstance(val, str):
                            target[part] = val.strip()
                        elif transform_type == "replace" and isinstance(val, str):
                            old = transform_config.get("old", "")
                            new = transform_config.get("new", "")
                            target[part] = val.replace(old, new)
                        elif transform_type == "prefix" and isinstance(val, str):
                            target[part] = transform_config.get("value", "") + val
                        elif transform_type == "suffix" and isinstance(val, str):
                            target[part] = val + transform_config.get("value", "")
                        elif transform_type == "int" and val is not None:
                            try:
                                target[part] = int(val)
                            except (ValueError, TypeError):
                                pass
                        elif transform_type == "float" and val is not None:
                            try:
                                target[part] = float(val)
                            except (ValueError, TypeError):
                                pass
                        elif transform_type == "default" and val is None:
                            target[part] = transform_config.get("value")
                    else:
                        target = target[part]

        return result

    def get_ingestion_stats(self, org_id: str) -> dict:
        self._telemetry["get_ingestion_stats_calls"] += 1
        org_jobs = [j for j in self._jobs.values() if j.org_id == org_id]
        org_connectors = [c for c in self._connectors.values() if c.org_id == org_id]
        org_batches = [b for b in self._batches.values() if b.org_id == org_id]
        org_mappings = [m for m in self._mappings.values() if m.org_id == org_id]
        org_metrics_list = [m for m in self._metrics.values() if m.org_id == org_id]

        by_status: dict[str, int] = defaultdict(int)
        by_source_type: dict[str, int] = defaultdict(int)
        by_mode: dict[str, int] = defaultdict(int)
        total_records_processed = 0
        total_records_failed = 0

        for j in org_jobs:
            by_status[j.status.value] += 1
            by_source_type[j.source_type.value] += 1
            by_mode[j.mode.value] += 1
            total_records_processed += j.records_processed
            total_records_failed += j.records_failed

        active_connectors = sum(1 for c in org_connectors if c.enabled)
        total_batches = len(org_batches)
        total_metrics = len(org_metrics_list)

        return {
            "org_id": org_id,
            "total_jobs": len(org_jobs),
            "total_connectors": len(org_connectors),
            "active_connectors": active_connectors,
            "total_mappings": len(org_mappings),
            "total_batches": total_batches,
            "total_metrics_records": total_metrics,
            "total_records_processed": total_records_processed,
            "total_records_failed": total_records_failed,
            "by_status": dict(by_status),
            "by_source_type": dict(by_source_type),
            "by_mode": dict(by_mode),
        }

    def get_telemetry(self) -> dict:
        self._telemetry["get_telemetry_calls"] += 1
        return dict(self._telemetry)
