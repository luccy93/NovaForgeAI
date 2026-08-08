import json
import uuid
import hashlib
import time
import math
import os
import logging
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


class AggregationLevel(Enum):
    RAW = "raw"
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


class DataEntity(Enum):
    COST_ENTRY = "cost_entry"
    USAGE_DATAPOINT = "usage_datapoint"
    INVOICE = "invoice"
    SUBSCRIPTION = "subscription"
    ALERT_EVENT = "alert_event"
    ROI_METRIC = "roi_metric"
    FORECAST_RESULT = "forecast_result"
    BUDGET_SNAPSHOT = "budget_snapshot"
    INFRA_COST = "infra_cost"
    USER_ACTIVITY = "user_activity"


class RetentionPolicy(Enum):
    DELETE_AFTER = "delete_after"
    ARCHIVE_AFTER = "archive_after"
    KEEP_FOREVER = "keep_forever"


class WarehouseStatus(Enum):
    ACTIVE = "active"
    ARCHIVING = "archiving"
    ARCHIVED = "archived"
    PURGING = "purging"
    ERROR = "error"


@dataclass
class WarehouseConfig:
    id: str
    org_id: str
    name: str
    data_entity: DataEntity
    aggregation: AggregationLevel
    retention_days: int = 90
    retention_policy: RetentionPolicy = RetentionPolicy.DELETE_AFTER
    archive_location: str = ""
    compress_data: bool = True
    enabled: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["data_entity"] = self.data_entity.value
        d["aggregation"] = self.aggregation.value
        d["retention_policy"] = self.retention_policy.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "WarehouseConfig":
        data = data.copy()
        data["data_entity"] = DataEntity(data.get("data_entity", "cost_entry"))
        data["aggregation"] = AggregationLevel(data.get("aggregation", "raw"))
        data["retention_policy"] = RetentionPolicy(data.get("retention_policy", "delete_after"))
        return cls(**data)


@dataclass
class AggregatedRecord:
    id: str
    org_id: str
    data_entity: DataEntity
    aggregation: AggregationLevel
    period_start: str
    period_end: str
    total_count: int = 0
    total_value: float = 0.0
    avg_value: float = 0.0
    min_value: float = 0.0
    max_value: float = 0.0
    dimensions: dict = field(default_factory=dict)
    record_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["data_entity"] = self.data_entity.value
        d["aggregation"] = self.aggregation.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AggregatedRecord":
        data = data.copy()
        data["data_entity"] = DataEntity(data.get("data_entity", "cost_entry"))
        data["aggregation"] = AggregationLevel(data.get("aggregation", "raw"))
        return cls(**data)


@dataclass
class DataArchive:
    id: str
    org_id: str
    name: str
    data_entity: DataEntity
    period_start: str
    period_end: str
    record_count: int = 0
    archive_path: str = ""
    size_bytes: int = 0
    checksum: str = ""
    archived_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["data_entity"] = self.data_entity.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "DataArchive":
        data = data.copy()
        data["data_entity"] = DataEntity(data.get("data_entity", "cost_entry"))
        return cls(**data)


@dataclass
class TrendSegment:
    id: str
    org_id: str
    metric_name: str
    aggregation: AggregationLevel
    period_start: str
    period_end: str
    data_points: list[dict] = field(default_factory=list)
    trend_line: list = field(default_factory=list)
    seasonality: dict = field(default_factory=dict)
    anomalies: list = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["aggregation"] = self.aggregation.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "TrendSegment":
        data = data.copy()
        data["aggregation"] = AggregationLevel(data.get("aggregation", "daily"))
        return cls(**data)


class DataWarehouse:
    def __init__(self, storage_dir: str = "warehouse_data"):
        self.storage_dir = storage_dir
        self._configs: dict[str, WarehouseConfig] = {}
        self._raw_data: dict[str, list[dict]] = defaultdict(list)
        self._aggregated: dict[str, AggregatedRecord] = {}
        self._archives: dict[str, DataArchive] = {}
        self._trends: dict[str, TrendSegment] = {}
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _configs_path(self) -> str:
        return os.path.join(self.storage_dir, "warehouse_configs.json")

    def _raw_data_path(self) -> str:
        return os.path.join(self.storage_dir, "raw_data.json")

    def _aggregated_path(self) -> str:
        return os.path.join(self.storage_dir, "aggregated.json")

    def _archives_path(self) -> str:
        return os.path.join(self.storage_dir, "archives.json")

    def _trends_path(self) -> str:
        return os.path.join(self.storage_dir, "trends.json")

    def _entity_config_key(self, org_id: str, entity: DataEntity) -> str:
        return f"{org_id}:{entity.value}"

    def _save(self) -> None:
        try:
            configs_data = {cid: c.to_dict() for cid, c in self._configs.items()}
            with open(self._configs_path(), "w", encoding="utf-8") as f:
                json.dump(configs_data, f, indent=2, default=str)

            raw_data = {k: v for k, v in self._raw_data.items()}
            with open(self._raw_data_path(), "w", encoding="utf-8") as f:
                json.dump(raw_data, f, indent=2, default=str)

            agg_data = {aid: a.to_dict() for aid, a in self._aggregated.items()}
            with open(self._aggregated_path(), "w", encoding="utf-8") as f:
                json.dump(agg_data, f, indent=2, default=str)

            archives_data = {aid: a.to_dict() for aid, a in self._archives.items()}
            with open(self._archives_path(), "w", encoding="utf-8") as f:
                json.dump(archives_data, f, indent=2, default=str)

            trends_data = {tid: t.to_dict() for tid, t in self._trends.items()}
            with open(self._trends_path(), "w", encoding="utf-8") as f:
                json.dump(trends_data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save warehouse data: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._configs_path()):
                with open(self._configs_path(), "r", encoding="utf-8") as f:
                    configs_data = json.load(f)
                for cid, data in configs_data.items():
                    try:
                        self._configs[cid] = WarehouseConfig.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed warehouse config %s: %s", cid, e)

            if os.path.exists(self._raw_data_path()):
                with open(self._raw_data_path(), "r", encoding="utf-8") as f:
                    raw_data = json.load(f)
                for key, entries in raw_data.items():
                    self._raw_data[key] = entries

            if os.path.exists(self._aggregated_path()):
                with open(self._aggregated_path(), "r", encoding="utf-8") as f:
                    agg_data = json.load(f)
                for aid, data in agg_data.items():
                    try:
                        self._aggregated[aid] = AggregatedRecord.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed aggregated record %s: %s", aid, e)

            if os.path.exists(self._archives_path()):
                with open(self._archives_path(), "r", encoding="utf-8") as f:
                    archives_data = json.load(f)
                for aid, data in archives_data.items():
                    try:
                        self._archives[aid] = DataArchive.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed archive %s: %s", aid, e)

            if os.path.exists(self._trends_path()):
                with open(self._trends_path(), "r", encoding="utf-8") as f:
                    trends_data = json.load(f)
                for tid, data in trends_data.items():
                    try:
                        self._trends[tid] = TrendSegment.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed trend segment %s: %s", tid, e)
        except Exception as e:
            logger.error("Failed to load warehouse data: %s", e, exc_info=True)

    def configure(self, config: WarehouseConfig) -> WarehouseConfig:
        self._telemetry["configure_calls"] += 1
        if not config.id:
            config.id = str(uuid.uuid4())
        config.updated_at = datetime.now(timezone.utc).isoformat()
        key = self._entity_config_key(config.org_id, config.data_entity)
        self._configs[key] = config
        self._save()
        logger.info("Configured warehouse for org %s entity %s: %s", config.org_id, config.data_entity.value, config.name)
        return config

    def get_config(self, org_id: str, data_entity: DataEntity) -> Optional[WarehouseConfig]:
        self._telemetry["get_config_calls"] += 1
        key = self._entity_config_key(org_id, data_entity)
        return self._configs.get(key)

    def _raw_key(self, org_id: str, entity: DataEntity) -> str:
        return f"{org_id}:{entity.value}"

    def ingest_record(self, entity: DataEntity, data: dict) -> bool:
        self._telemetry["ingest_record_calls"] += 1
        try:
            org_id = data.get("org_id", "")
            if not org_id:
                logger.warning("ingest_record missing org_id")
                return False
            key = self._raw_key(org_id, entity)
            record = {
                "id": str(uuid.uuid4()),
                "org_id": org_id,
                "entity": entity.value,
                "data": data,
                "timestamp": data.get("timestamp", datetime.now(timezone.utc).isoformat()),
                "ingested_at": datetime.now(timezone.utc).isoformat(),
            }
            self._raw_data[key].append(record)
            self._save()
            logger.debug("Ingested %s record for org %s", entity.value, org_id)
            return True
        except Exception as e:
            logger.error("Failed to ingest record: %s", e, exc_info=True)
            return False

    def run_aggregation(self, org_id: str, entity: DataEntity, aggregation: AggregationLevel) -> AggregatedRecord:
        self._telemetry["run_aggregation_calls"] += 1
        key = self._raw_key(org_id, entity)
        raw_entries = self._raw_data.get(key, [])

        now = datetime.now(timezone.utc)
        if aggregation == AggregationLevel.HOURLY:
            period_start = now - timedelta(hours=1)
        elif aggregation == AggregationLevel.DAILY:
            period_start = now - timedelta(days=1)
        elif aggregation == AggregationLevel.WEEKLY:
            period_start = now - timedelta(weeks=1)
        elif aggregation == AggregationLevel.MONTHLY:
            period_start = now - timedelta(days=30)
        elif aggregation == AggregationLevel.QUARTERLY:
            period_start = now - timedelta(days=91)
        elif aggregation == AggregationLevel.YEARLY:
            period_start = now - timedelta(days=365)
        else:
            period_start = now - timedelta(days=1)

        filtered = [
            e for e in raw_entries
            if e.get("timestamp", "").startswith(period_start.strftime("%Y-%m-%d")) or
               datetime.fromisoformat(e.get("timestamp", now.isoformat())) >= period_start
        ]

        total_count = len(filtered)
        values = []
        for entry in filtered:
            val = entry.get("data", {}).get("value", 0.0)
            if isinstance(val, (int, float)):
                values.append(val)

        total_value = sum(values)
        avg_value = round(total_value / max(len(values), 1), 4)
        min_value = round(min(values), 4) if values else 0.0
        max_value = round(max(values), 4) if values else 0.0

        dimensions: dict = defaultdict(float)
        for entry in filtered:
            dims = entry.get("data", {}).get("dimensions", {})
            for k, v in dims.items():
                if isinstance(v, (int, float)):
                    dimensions[k] += v

        record = AggregatedRecord(
            id=str(uuid.uuid4()),
            org_id=org_id,
            data_entity=entity,
            aggregation=aggregation,
            period_start=period_start.isoformat(),
            period_end=now.isoformat(),
            total_count=total_count,
            total_value=round(total_value, 4),
            avg_value=avg_value,
            min_value=min_value,
            max_value=max_value,
            dimensions=dict(dimensions),
            record_count=len(filtered),
        )
        self._aggregated[record.id] = record
        self._save()
        logger.info("Ran %s aggregation for org %s entity %s: records=%d, total=%.2f",
                     aggregation.value, org_id, entity.value, total_count, total_value)
        return record

    def run_daily_aggregation(self, org_id: str) -> list[AggregatedRecord]:
        self._telemetry["run_daily_aggregation_calls"] += 1
        results = []
        for entity in DataEntity:
            config_key = self._entity_config_key(org_id, entity)
            config = self._configs.get(config_key)
            if config and not config.enabled:
                continue
            record = self.run_aggregation(org_id, entity, AggregationLevel.DAILY)
            results.append(record)
        return results

    def run_monthly_aggregation(self, org_id: str) -> list[AggregatedRecord]:
        self._telemetry["run_monthly_aggregation_calls"] += 1
        results = []
        for entity in DataEntity:
            config_key = self._entity_config_key(org_id, entity)
            config = self._configs.get(config_key)
            if config and not config.enabled:
                continue
            record = self.run_aggregation(org_id, entity, AggregationLevel.MONTHLY)
            results.append(record)
        return results

    def run_yearly_aggregation(self, org_id: str) -> list[AggregatedRecord]:
        self._telemetry["run_yearly_aggregation_calls"] += 1
        results = []
        for entity in DataEntity:
            config_key = self._entity_config_key(org_id, entity)
            config = self._configs.get(config_key)
            if config and not config.enabled:
                continue
            record = self.run_aggregation(org_id, entity, AggregationLevel.YEARLY)
            results.append(record)
        return results

    def get_aggregated_data(self, org_id: str, entity: DataEntity, aggregation: AggregationLevel,
                            start_date: str, end_date: str) -> list[AggregatedRecord]:
        self._telemetry["get_aggregated_data_calls"] += 1
        results = []
        for record in self._aggregated.values():
            if (record.org_id == org_id and record.data_entity == entity
                    and record.aggregation == aggregation
                    and record.period_start >= start_date
                    and record.period_end <= end_date):
                results.append(record)
        results.sort(key=lambda r: r.period_start)
        return results

    def analyze_trends(self, org_id: str, metric_name: str, aggregation: AggregationLevel,
                       periods: int = 12) -> TrendSegment:
        self._telemetry["analyze_trends_calls"] += 1
        now = datetime.now(timezone.utc)

        if aggregation == AggregationLevel.DAILY:
            period_start = now - timedelta(days=periods)
            period_end = now
        elif aggregation == AggregationLevel.WEEKLY:
            period_start = now - timedelta(weeks=periods)
            period_end = now
        elif aggregation == AggregationLevel.MONTHLY:
            period_start = now - timedelta(days=periods * 30)
            period_end = now
        elif aggregation == AggregationLevel.QUARTERLY:
            period_start = now - timedelta(days=periods * 91)
            period_end = now
        elif aggregation == AggregationLevel.YEARLY:
            period_start = now - timedelta(days=periods * 365)
            period_end = now
        else:
            period_start = now - timedelta(days=periods)
            period_end = now

        data_points = []
        values = []
        for record in self._aggregated.values():
            if record.org_id == org_id and record.aggregation == aggregation:
                ts = datetime.fromisoformat(record.created_at)
                if period_start <= ts <= period_end:
                    pt = {
                        "date": record.period_start[:10],
                        "value": record.total_value,
                        "count": record.total_count,
                        "entity": record.data_entity.value,
                    }
                    data_points.append(pt)
                    values.append(record.total_value)

        if not values:
            values = [0.0]

        n = len(values)
        x_vals = list(range(n))
        sum_x = sum(x_vals)
        sum_y = sum(values)
        sum_xy = sum(x * y for x, y in zip(x_vals, values))
        sum_xx = sum(x * x for x in x_vals)
        denom = n * sum_xx - sum_x * sum_x
        if denom == 0:
            slope = 0.0
            intercept = sum_y / max(n, 1)
        else:
            slope = (n * sum_xy - sum_x * sum_y) / denom
            intercept = (sum_y - slope * sum_x) / max(n, 1)

        trend_line = []
        for i in range(min(periods, 24)):
            x_pred = n + i
            val = intercept + slope * x_pred
            trend_line.append({"period": i + 1, "predicted": round(max(0, val), 4)})

        seasonality = {}
        if len(values) >= 8:
            mid = len(values) // 2
            first_half = sum(values[:mid]) / max(mid, 1)
            second_half = sum(values[mid:]) / max(len(values) - mid, 1)
            if first_half > 0:
                seasonality["strength"] = round(abs(second_half - first_half) / first_half, 4)
            else:
                seasonality["strength"] = 0.0
            seasonality["has_seasonality"] = seasonality["strength"] > 0.2
            seasonality["first_half_avg"] = round(first_half, 4)
            seasonality["second_half_avg"] = round(second_half, 4)
        else:
            seasonality = {"has_seasonality": False, "strength": 0.0, "note": "Insufficient data"}

        anomalies = []
        if values:
            mean = sum(values) / len(values)
            variance = sum((v - mean) ** 2 for v in values) / len(values)
            std_dev = math.sqrt(variance)
            threshold = 2.0 * std_dev
            for i, v in enumerate(values):
                if abs(v - mean) > threshold:
                    anomalies.append({
                        "index": i,
                        "value": round(v, 4),
                        "expected": round(mean, 4),
                        "deviation": round(v - mean, 4),
                        "severity": "high" if abs(v - mean) > 3 * std_dev else "medium",
                    })

        segment = TrendSegment(
            id=str(uuid.uuid4()),
            org_id=org_id,
            metric_name=metric_name,
            aggregation=aggregation,
            period_start=period_start.isoformat(),
            period_end=period_end.isoformat(),
            data_points=data_points,
            trend_line=trend_line,
            seasonality=seasonality,
            anomalies=anomalies,
        )
        self._trends[segment.id] = segment
        self._save()
        logger.info("Analyzed trends for org %s metric %s: %d points, %d anomalies",
                     org_id, metric_name, len(data_points), len(anomalies))
        return segment

    def archive_data(self, org_id: str, entity: DataEntity, older_than_days: int) -> DataArchive:
        self._telemetry["archive_data_calls"] += 1
        key = self._raw_key(org_id, entity)
        cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
        cutoff_str = cutoff.isoformat()

        to_archive = []
        remaining = []
        for entry in self._raw_data.get(key, []):
            ts = entry.get("timestamp", "")
            if ts < cutoff_str:
                to_archive.append(entry)
            else:
                remaining.append(entry)

        if not to_archive:
            archive = DataArchive(
                id=str(uuid.uuid4()),
                org_id=org_id,
                name=f"archive_{entity.value}_{cutoff.strftime('%Y%m%d')}",
                data_entity=entity,
                period_start="",
                period_end="",
                record_count=0,
                archive_path="",
                size_bytes=0,
                checksum="",
            )
            self._archives[archive.id] = archive
            self._save()
            return archive

        archive_data_str = json.dumps(to_archive, default=str)
        size_bytes = len(archive_data_str.encode("utf-8"))
        checksum = hashlib.sha256(archive_data_str.encode("utf-8")).hexdigest()

        archive_name = f"archive_{entity.value}_{cutoff.strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}"
        archive_path = os.path.join(self.storage_dir, f"{archive_name}.json")
        try:
            with open(archive_path, "w", encoding="utf-8") as f:
                json.dump(to_archive, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to write archive file: %s", e, exc_info=True)
            archive_path = ""

        self._raw_data[key] = remaining

        timestamps = [e.get("timestamp", "") for e in to_archive if e.get("timestamp")]
        period_start = min(timestamps) if timestamps else ""
        period_end = max(timestamps) if timestamps else ""

        archive = DataArchive(
            id=str(uuid.uuid4()),
            org_id=org_id,
            name=archive_name,
            data_entity=entity,
            period_start=period_start,
            period_end=period_end,
            record_count=len(to_archive),
            archive_path=archive_path,
            size_bytes=size_bytes,
            checksum=checksum,
        )
        self._archives[archive.id] = archive
        self._save()
        logger.info("Archived %d records for org %s entity %s (older than %d days)",
                     len(to_archive), org_id, entity.value, older_than_days)
        return archive

    def purge_data(self, org_id: str, entity: DataEntity, older_than_days: int) -> int:
        self._telemetry["purge_data_calls"] += 1
        key = self._raw_key(org_id, entity)
        cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
        cutoff_str = cutoff.isoformat()

        original_count = len(self._raw_data.get(key, []))
        self._raw_data[key] = [
            entry for entry in self._raw_data.get(key, [])
            if entry.get("timestamp", "") >= cutoff_str
        ]
        purged = original_count - len(self._raw_data[key])

        agg_to_remove = []
        for aid, record in self._aggregated.items():
            if record.org_id == org_id and record.data_entity == entity:
                ts = datetime.fromisoformat(record.created_at)
                if ts < cutoff:
                    agg_to_remove.append(aid)
        for aid in agg_to_remove:
            del self._aggregated[aid]

        self._save()
        if purged > 0:
            logger.info("Purged %d records for org %s entity %s (older than %d days)",
                         purged, org_id, entity.value, older_than_days)
        return purged

    def get_warehouse_stats(self, org_id: str) -> dict:
        self._telemetry["get_warehouse_stats_calls"] += 1
        record_counts: dict[str, int] = defaultdict(int)
        storage_used = 0
        last_aggregation = ""
        total_records = 0

        for key, entries in self._raw_data.items():
            if key.startswith(f"{org_id}:"):
                entity_name = key.split(":", 1)[1] if ":" in key else key
                count = len(entries)
                record_counts[entity_name] = count
                total_records += count

        for record in self._aggregated.values():
            if record.org_id == org_id:
                if not last_aggregation or record.created_at > last_aggregation:
                    last_aggregation = record.created_at

        storage_paths = [
            self._configs_path(), self._raw_data_path(), self._aggregated_path(),
            self._archives_path(), self._trends_path(),
        ]
        for sp in storage_paths:
            if os.path.exists(sp):
                storage_used += os.path.getsize(sp)

        return {
            "org_id": org_id,
            "total_records": total_records,
            "record_counts": dict(record_counts),
            "storage_used_bytes": storage_used,
            "storage_used_mb": round(storage_used / (1024 * 1024), 4),
            "aggregated_records": len([r for r in self._aggregated.values() if r.org_id == org_id]),
            "archives": len([a for a in self._archives.values() if a.org_id == org_id]),
            "trend_segments": len([t for t in self._trends.values() if t.org_id == org_id]),
            "last_aggregation": last_aggregation or "never",
            "configs": len([c for c in self._configs.values() if c.org_id == org_id]),
        }

    def get_telemetry(self) -> dict:
        self._telemetry["get_telemetry_calls"] += 1
        return dict(self._telemetry)
