"""
Resource Management — Repository Quotas, Storage Quotas, Token Quotas, Embedding Quotas, Agent Quotas, Worker Quotas.
"""
import logging
logger = logging.getLogger(__name__)

from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
import json, uuid, hashlib, time, os
from collections import defaultdict


class QuotaType(Enum):
    REPOSITORY = "repository"
    STORAGE = "storage"
    TOKENS = "tokens"
    EMBEDDINGS = "embeddings"
    AGENTS = "agents"
    WORKERS = "workers"
    API_CALLS = "api_calls"
    COMPUTE_TIME = "compute_time"


class QuotaPeriod(Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    LIFETIME = "lifetime"


class QuotaStatus(Enum):
    ACTIVE = "active"
    NEARING_LIMIT = "nearing_limit"
    EXCEEDED = "exceeded"
    WAIVED = "waived"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ResourceQuota:
    id: str
    org_id: str
    workspace_id: Optional[str]
    project_id: Optional[str]
    quota_type: QuotaType
    period: QuotaPeriod
    limit: float
    used: float
    remaining: float
    unit: str
    status: QuotaStatus
    reset_at: str
    created_at: str
    updated_at: str
    overage_allowed: bool = False
    overage_rate: float = 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["quota_type"] = self.quota_type.value
        d["period"] = self.period.value
        d["status"] = self.status.value
        return d

    @staticmethod
    def from_dict(data: dict) -> "ResourceQuota":
        data = dict(data)
        data["quota_type"] = QuotaType(data["quota_type"])
        data["period"] = QuotaPeriod(data["period"])
        data["status"] = QuotaStatus(data["status"])
        return ResourceQuota(**data)


@dataclass
class QuotaLimit:
    id: str
    quota_type: QuotaType
    default_limit: float
    max_limit: float
    unit: str
    can_increase: bool = False
    increase_cost: float = 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["quota_type"] = self.quota_type.value
        return d

    @staticmethod
    def from_dict(data: dict) -> "QuotaLimit":
        data = dict(data)
        data["quota_type"] = QuotaType(data["quota_type"])
        return QuotaLimit(**data)


@dataclass
class QuotaUsage:
    quota_id: str
    quota_type: QuotaType
    period_start: str
    period_end: str
    used: float = 0.0
    limit: float = 0.0
    usage_percent: float = 0.0
    peak_usage: float = 0.0
    avg_daily_usage: float = 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["quota_type"] = self.quota_type.value
        return d

    @staticmethod
    def from_dict(data: dict) -> "QuotaUsage":
        data = dict(data)
        data["quota_type"] = QuotaType(data["quota_type"])
        return QuotaUsage(**data)


@dataclass
class QuotaAlert:
    id: str
    quota_id: str
    quota_type: QuotaType
    threshold: float
    current_usage: float
    message: str
    created_at: str
    acknowledged: bool = False
    severity: str = "warning"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["quota_type"] = self.quota_type.value
        return d

    @staticmethod
    def from_dict(data: dict) -> "QuotaAlert":
        data = dict(data)
        data["quota_type"] = QuotaType(data["quota_type"])
        return QuotaAlert(**data)


@dataclass
class BillingMetric:
    id: str
    org_id: str
    metric_type: str
    quantity: float
    unit: str
    rate: float
    cost: float
    timestamp: str
    period: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "BillingMetric":
        return BillingMetric(**data)


# ---------------------------------------------------------------------------
# Managers
# ---------------------------------------------------------------------------

class RepositoryQuotaManager:
    """Manages repository quotas with JSON persistence."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._quotas_file = os.path.join(storage_dir, "repo_quotas.json")
        self._quotas: dict[str, ResourceQuota] = {}
        self._limits_file = os.path.join(storage_dir, "quota_limits.json")
        self._limits: dict[str, QuotaLimit] = {}
        self._usage_file = os.path.join(storage_dir, "quota_usage.json")
        self._usages: dict[str, QuotaUsage] = {}
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self._quotas_file):
                with open(self._quotas_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._quotas = {k: ResourceQuota.from_dict(v) for k, v in data.items()}
                logger.info("Loaded %d repository quotas", len(self._quotas))
        except Exception:
            logger.exception("Failed to load repo quotas; starting fresh")
            self._quotas = {}
        try:
            if os.path.exists(self._limits_file):
                with open(self._limits_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._limits = {k: QuotaLimit.from_dict(v) for k, v in data.items()}
        except Exception:
            self._limits = {}
        try:
            if os.path.exists(self._usage_file):
                with open(self._usage_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._usages = {k: QuotaUsage.from_dict(v) for k, v in data.items()}
        except Exception:
            self._usages = {}

    def _save(self) -> None:
        try:
            data = {k: v.to_dict() for k, v in self._quotas.items()}
            tmp = self._quotas_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._quotas_file)
        except Exception:
            logger.exception("Failed to save repo quotas")
        try:
            data = {k: v.to_dict() for k, v in self._limits.items()}
            tmp = self._limits_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._limits_file)
        except Exception:
            logger.exception("Failed to save quota limits")
        try:
            data = {k: v.to_dict() for k, v in self._usages.items()}
            tmp = self._usage_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._usage_file)
        except Exception:
            logger.exception("Failed to save quota usage")

    def set_quota(self, org_id: str, quota_type: QuotaType, limit: float, unit: str,
                  workspace_id: Optional[str] = None, project_id: Optional[str] = None,
                  period: QuotaPeriod = QuotaPeriod.MONTHLY,
                  overage_allowed: bool = False, overage_rate: float = 0.0) -> ResourceQuota:
        try:
            now = datetime.now(timezone.utc).isoformat()
            reset_at = datetime.now(timezone.utc).isoformat()
            used = 0.0
            remaining = limit - used
            status = QuotaStatus.ACTIVE
            qid = str(uuid.uuid4())
            quota = ResourceQuota(
                id=qid, org_id=org_id, workspace_id=workspace_id, project_id=project_id,
                quota_type=quota_type, period=period, limit=limit, used=used,
                remaining=remaining, unit=unit, status=status, reset_at=reset_at,
                created_at=now, updated_at=now, overage_allowed=overage_allowed,
                overage_rate=overage_rate,
            )
            self._quotas[qid] = quota
            self._save()
            self.telemetry["repo_quotas_set"] += 1
            logger.info("Set quota %s for org %s type %s limit %f", qid, org_id, quota_type.value, limit)
            return quota
        except Exception:
            logger.exception("Failed to set repo quota")
            raise

    def get_quota(self, quota_id: str) -> ResourceQuota:
        quota = self._quotas.get(quota_id)
        if quota is None:
            raise ValueError(f"Repository quota not found: {quota_id}")
        self.telemetry["repo_quotas_read"] += 1
        return quota

    def check_quota(self, quota_id: str) -> dict:
        try:
            quota = self.get_quota(quota_id)
            usage_pct = (quota.used / quota.limit * 100) if quota.limit > 0 else 0
            if usage_pct >= 100:
                quota.status = QuotaStatus.EXCEEDED
            elif usage_pct >= 80:
                quota.status = QuotaStatus.NEARING_LIMIT
            else:
                quota.status = QuotaStatus.ACTIVE
            quota.remaining = max(0, quota.limit - quota.used)
            quota.updated_at = datetime.now(timezone.utc).isoformat()
            self._quotas[quota_id] = quota
            self._save()
            self.telemetry["repo_quotas_checked"] += 1
            return {
                "quota_id": quota_id,
                "allowed": usage_pct < 100 or quota.overage_allowed,
                "used": quota.used,
                "limit": quota.limit,
                "remaining": quota.remaining,
                "usage_percent": round(usage_pct, 2),
                "status": quota.status.value,
                "overage_allowed": quota.overage_allowed,
            }
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to check repo quota %s", quota_id)
            raise

    def increment_usage(self, quota_id: str, amount: float) -> ResourceQuota:
        try:
            quota = self.get_quota(quota_id)
            quota.used += amount
            quota.remaining = max(0, quota.limit - quota.used)
            usage_pct = (quota.used / quota.limit * 100) if quota.limit > 0 else 0
            if usage_pct >= 100:
                quota.status = QuotaStatus.EXCEEDED
            elif usage_pct >= 80:
                quota.status = QuotaStatus.NEARING_LIMIT
            quota.updated_at = datetime.now(timezone.utc).isoformat()
            self._quotas[quota_id] = quota
            self._save()
            self.telemetry["repo_usage_incremented"] += 1
            logger.info("Incremented quota %s by %f (total: %f)", quota_id, amount, quota.used)
            return quota
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to increment quota %s", quota_id)
            raise

    def decrement_usage(self, quota_id: str, amount: float) -> ResourceQuota:
        try:
            quota = self.get_quota(quota_id)
            quota.used = max(0, quota.used - amount)
            quota.remaining = quota.limit - quota.used
            usage_pct = (quota.used / quota.limit * 100) if quota.limit > 0 else 0
            if usage_pct < 80:
                quota.status = QuotaStatus.ACTIVE
            elif usage_pct < 100:
                quota.status = QuotaStatus.NEARING_LIMIT
            quota.updated_at = datetime.now(timezone.utc).isoformat()
            self._quotas[quota_id] = quota
            self._save()
            self.telemetry["repo_usage_decremented"] += 1
            logger.info("Decremented quota %s by %f (total: %f)", quota_id, amount, quota.used)
            return quota
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to decrement quota %s", quota_id)
            raise

    def get_usage_report(self, org_id: Optional[str] = None) -> dict:
        try:
            quotas = list(self._quotas.values())
            if org_id:
                quotas = [q for q in quotas if q.org_id == org_id]
            total_used = sum(q.used for q in quotas)
            total_limit = sum(q.limit for q in quotas)
            exceeded = [q for q in quotas if q.status == QuotaStatus.EXCEEDED]
            nearing = [q for q in quotas if q.status == QuotaStatus.NEARING_LIMIT]
            report = {
                "total_quotas": len(quotas),
                "total_used": total_used,
                "total_limit": total_limit,
                "exceeded_count": len(exceeded),
                "nearing_limit_count": len(nearing),
                "quotas": [q.to_dict() for q in quotas],
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
            self.telemetry["repo_reports_generated"] += 1
            return report
        except Exception:
            logger.exception("Failed to generate repo usage report")
            raise


class StorageQuotaManager:
    """Manages storage quotas with JSON persistence."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._quotas_file = os.path.join(storage_dir, "storage_quotas.json")
        self._quotas: dict[str, ResourceQuota] = {}
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self._quotas_file):
                with open(self._quotas_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._quotas = {k: ResourceQuota.from_dict(v) for k, v in data.items()}
                logger.info("Loaded %d storage quotas", len(self._quotas))
        except Exception:
            logger.exception("Failed to load storage quotas; starting fresh")
            self._quotas = {}

    def _save(self) -> None:
        try:
            data = {k: v.to_dict() for k, v in self._quotas.items()}
            tmp = self._quotas_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._quotas_file)
        except Exception:
            logger.exception("Failed to save storage quotas")

    def set_storage_quota(self, org_id: str, limit: float, unit: str = "gb",
                           workspace_id: Optional[str] = None,
                           period: QuotaPeriod = QuotaPeriod.MONTHLY) -> ResourceQuota:
        try:
            now = datetime.now(timezone.utc).isoformat()
            qid = str(uuid.uuid4())
            quota = ResourceQuota(
                id=qid, org_id=org_id, workspace_id=workspace_id, project_id=None,
                quota_type=QuotaType.STORAGE, period=period, limit=limit, used=0.0,
                remaining=limit, unit=unit, status=QuotaStatus.ACTIVE, reset_at=now,
                created_at=now, updated_at=now,
            )
            self._quotas[qid] = quota
            self._save()
            self.telemetry["storage_quotas_set"] += 1
            logger.info("Set storage quota %s for org %s limit %f %s", qid, org_id, limit, unit)
            return quota
        except Exception:
            logger.exception("Failed to set storage quota")
            raise

    def get_storage_quota(self, quota_id: str) -> ResourceQuota:
        quota = self._quotas.get(quota_id)
        if quota is None:
            raise ValueError(f"Storage quota not found: {quota_id}")
        self.telemetry["storage_quotas_read"] += 1
        return quota

    def check_storage_quota(self, quota_id: str) -> dict:
        try:
            quota = self.get_storage_quota(quota_id)
            usage_pct = (quota.used / quota.limit * 100) if quota.limit > 0 else 0
            quota.remaining = max(0, quota.limit - quota.used)
            if usage_pct >= 100:
                quota.status = QuotaStatus.EXCEEDED
            elif usage_pct >= 80:
                quota.status = QuotaStatus.NEARING_LIMIT
            else:
                quota.status = QuotaStatus.ACTIVE
            quota.updated_at = datetime.now(timezone.utc).isoformat()
            self._quotas[quota_id] = quota
            self._save()
            self.telemetry["storage_quotas_checked"] += 1
            return {
                "quota_id": quota_id, "allowed": usage_pct < 100,
                "used": quota.used, "limit": quota.limit,
                "remaining": quota.remaining, "usage_percent": round(usage_pct, 2),
                "status": quota.status.value,
            }
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to check storage quota %s", quota_id)
            raise

    def track_usage(self, quota_id: str, bytes_used: float) -> ResourceQuota:
        return self.increment_usage(quota_id, bytes_used)

    def increment_usage(self, quota_id: str, amount: float) -> ResourceQuota:
        try:
            quota = self.get_storage_quota(quota_id)
            quota.used += amount
            quota.remaining = max(0, quota.limit - quota.used)
            usage_pct = (quota.used / quota.limit * 100) if quota.limit > 0 else 0
            if usage_pct >= 100:
                quota.status = QuotaStatus.EXCEEDED
            elif usage_pct >= 80:
                quota.status = QuotaStatus.NEARING_LIMIT
            quota.updated_at = datetime.now(timezone.utc).isoformat()
            self._quotas[quota_id] = quota
            self._save()
            self.telemetry["storage_usage_tracked"] += 1
            return quota
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to track storage usage for %s", quota_id)
            raise

    def get_storage_report(self, org_id: Optional[str] = None) -> dict:
        try:
            quotas = list(self._quotas.values())
            if org_id:
                quotas = [q for q in quotas if q.org_id == org_id]
            total_used = sum(q.used for q in quotas)
            total_limit = sum(q.limit for q in quotas)
            report = {
                "total_quotas": len(quotas), "total_used": total_used,
                "total_limit": total_limit,
                "usage_percent": round((total_used / total_limit * 100) if total_limit > 0 else 0, 2),
                "quotas": [q.to_dict() for q in quotas],
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
            self.telemetry["storage_reports_generated"] += 1
            return report
        except Exception:
            logger.exception("Failed to generate storage report")
            raise


class TokenQuotaManager:
    """Manages token quotas with JSON persistence."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._quotas_file = os.path.join(storage_dir, "token_quotas.json")
        self._quotas: dict[str, ResourceQuota] = {}
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self._quotas_file):
                with open(self._quotas_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._quotas = {k: ResourceQuota.from_dict(v) for k, v in data.items()}
                logger.info("Loaded %d token quotas", len(self._quotas))
        except Exception:
            logger.exception("Failed to load token quotas; starting fresh")
            self._quotas = {}

    def _save(self) -> None:
        try:
            data = {k: v.to_dict() for k, v in self._quotas.items()}
            tmp = self._quotas_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._quotas_file)
        except Exception:
            logger.exception("Failed to save token quotas")

    def set_token_quota(self, org_id: str, limit: float, unit: str = "tokens",
                         workspace_id: Optional[str] = None,
                         period: QuotaPeriod = QuotaPeriod.DAILY) -> ResourceQuota:
        try:
            now = datetime.now(timezone.utc).isoformat()
            qid = str(uuid.uuid4())
            quota = ResourceQuota(
                id=qid, org_id=org_id, workspace_id=workspace_id, project_id=None,
                quota_type=QuotaType.TOKENS, period=period, limit=limit, used=0.0,
                remaining=limit, unit=unit, status=QuotaStatus.ACTIVE, reset_at=now,
                created_at=now, updated_at=now,
            )
            self._quotas[qid] = quota
            self._save()
            self.telemetry["token_quotas_set"] += 1
            logger.info("Set token quota %s for org %s limit %f", qid, org_id, limit)
            return quota
        except Exception:
            logger.exception("Failed to set token quota")
            raise

    def get_token_quota(self, quota_id: str) -> ResourceQuota:
        quota = self._quotas.get(quota_id)
        if quota is None:
            raise ValueError(f"Token quota not found: {quota_id}")
        self.telemetry["token_quotas_read"] += 1
        return quota

    def track_token_usage(self, quota_id: str, tokens: float) -> ResourceQuota:
        try:
            quota = self.get_token_quota(quota_id)
            quota.used += tokens
            quota.remaining = max(0, quota.limit - quota.used)
            usage_pct = (quota.used / quota.limit * 100) if quota.limit > 0 else 0
            if usage_pct >= 100:
                quota.status = QuotaStatus.EXCEEDED
            elif usage_pct >= 80:
                quota.status = QuotaStatus.NEARING_LIMIT
            quota.updated_at = datetime.now(timezone.utc).isoformat()
            self._quotas[quota_id] = quota
            self._save()
            self.telemetry["token_usage_tracked"] += 1
            return quota
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to track token usage for %s", quota_id)
            raise

    def check_token_quota(self, quota_id: str) -> dict:
        try:
            quota = self.get_token_quota(quota_id)
            usage_pct = (quota.used / quota.limit * 100) if quota.limit > 0 else 0
            quota.remaining = max(0, quota.limit - quota.used)
            if usage_pct >= 100:
                quota.status = QuotaStatus.EXCEEDED
            elif usage_pct >= 80:
                quota.status = QuotaStatus.NEARING_LIMIT
            else:
                quota.status = QuotaStatus.ACTIVE
            quota.updated_at = datetime.now(timezone.utc).isoformat()
            self._quotas[quota_id] = quota
            self._save()
            self.telemetry["token_quotas_checked"] += 1
            return {
                "quota_id": quota_id, "allowed": usage_pct < 100,
                "used": quota.used, "limit": quota.limit,
                "remaining": quota.remaining, "usage_percent": round(usage_pct, 2),
                "status": quota.status.value,
            }
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to check token quota %s", quota_id)
            raise

    def get_token_usage_report(self, org_id: Optional[str] = None) -> dict:
        try:
            quotas = list(self._quotas.values())
            if org_id:
                quotas = [q for q in quotas if q.org_id == org_id]
            total_used = sum(q.used for q in quotas)
            total_limit = sum(q.limit for q in quotas)
            report = {
                "total_quotas": len(quotas), "total_used": total_used,
                "total_limit": total_limit,
                "usage_percent": round((total_used / total_limit * 100) if total_limit > 0 else 0, 2),
                "quotas": [q.to_dict() for q in quotas],
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
            self.telemetry["token_reports_generated"] += 1
            return report
        except Exception:
            logger.exception("Failed to generate token usage report")
            raise


class EmbeddingQuotaManager:
    """Manages embedding quotas with JSON persistence."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._quotas_file = os.path.join(storage_dir, "embedding_quotas.json")
        self._quotas: dict[str, ResourceQuota] = {}
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self._quotas_file):
                with open(self._quotas_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._quotas = {k: ResourceQuota.from_dict(v) for k, v in data.items()}
                logger.info("Loaded %d embedding quotas", len(self._quotas))
        except Exception:
            logger.exception("Failed to load embedding quotas; starting fresh")
            self._quotas = {}

    def _save(self) -> None:
        try:
            data = {k: v.to_dict() for k, v in self._quotas.items()}
            tmp = self._quotas_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._quotas_file)
        except Exception:
            logger.exception("Failed to save embedding quotas")

    def set_embedding_quota(self, org_id: str, limit: float, unit: str = "vectors",
                             workspace_id: Optional[str] = None,
                             period: QuotaPeriod = QuotaPeriod.MONTHLY) -> ResourceQuota:
        try:
            now = datetime.now(timezone.utc).isoformat()
            qid = str(uuid.uuid4())
            quota = ResourceQuota(
                id=qid, org_id=org_id, workspace_id=workspace_id, project_id=None,
                quota_type=QuotaType.EMBEDDINGS, period=period, limit=limit, used=0.0,
                remaining=limit, unit=unit, status=QuotaStatus.ACTIVE, reset_at=now,
                created_at=now, updated_at=now,
            )
            self._quotas[qid] = quota
            self._save()
            self.telemetry["embedding_quotas_set"] += 1
            logger.info("Set embedding quota %s for org %s limit %f", qid, org_id, limit)
            return quota
        except Exception:
            logger.exception("Failed to set embedding quota")
            raise

    def get_embedding_quota(self, quota_id: str) -> ResourceQuota:
        quota = self._quotas.get(quota_id)
        if quota is None:
            raise ValueError(f"Embedding quota not found: {quota_id}")
        self.telemetry["embedding_quotas_read"] += 1
        return quota

    def track_embedding_usage(self, quota_id: str, vectors: float) -> ResourceQuota:
        try:
            quota = self.get_embedding_quota(quota_id)
            quota.used += vectors
            quota.remaining = max(0, quota.limit - quota.used)
            usage_pct = (quota.used / quota.limit * 100) if quota.limit > 0 else 0
            if usage_pct >= 100:
                quota.status = QuotaStatus.EXCEEDED
            elif usage_pct >= 80:
                quota.status = QuotaStatus.NEARING_LIMIT
            quota.updated_at = datetime.now(timezone.utc).isoformat()
            self._quotas[quota_id] = quota
            self._save()
            self.telemetry["embedding_usage_tracked"] += 1
            return quota
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to track embedding usage for %s", quota_id)
            raise

    def check_embedding_quota(self, quota_id: str) -> dict:
        try:
            quota = self.get_embedding_quota(quota_id)
            usage_pct = (quota.used / quota.limit * 100) if quota.limit > 0 else 0
            quota.remaining = max(0, quota.limit - quota.used)
            if usage_pct >= 100:
                quota.status = QuotaStatus.EXCEEDED
            elif usage_pct >= 80:
                quota.status = QuotaStatus.NEARING_LIMIT
            else:
                quota.status = QuotaStatus.ACTIVE
            quota.updated_at = datetime.now(timezone.utc).isoformat()
            self._quotas[quota_id] = quota
            self._save()
            self.telemetry["embedding_quotas_checked"] += 1
            return {
                "quota_id": quota_id, "allowed": usage_pct < 100,
                "used": quota.used, "limit": quota.limit,
                "remaining": quota.remaining, "usage_percent": round(usage_pct, 2),
                "status": quota.status.value,
            }
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to check embedding quota %s", quota_id)
            raise


class AgentQuotaManager:
    """Manages agent quotas with JSON persistence."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._quotas_file = os.path.join(storage_dir, "agent_quotas.json")
        self._quotas: dict[str, ResourceQuota] = {}
        self._agents_file = os.path.join(storage_dir, "agent_registry.json")
        self._agents: dict[str, dict] = {}
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self._quotas_file):
                with open(self._quotas_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._quotas = {k: ResourceQuota.from_dict(v) for k, v in data.items()}
                logger.info("Loaded %d agent quotas", len(self._quotas))
        except Exception:
            logger.exception("Failed to load agent quotas; starting fresh")
            self._quotas = {}
        try:
            if os.path.exists(self._agents_file):
                with open(self._agents_file, "r", encoding="utf-8") as fh:
                    self._agents = json.load(fh)
        except Exception:
            self._agents = {}

    def _save(self) -> None:
        try:
            data = {k: v.to_dict() for k, v in self._quotas.items()}
            tmp = self._quotas_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._quotas_file)
        except Exception:
            logger.exception("Failed to save agent quotas")
        try:
            tmp = self._agents_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._agents, fh, indent=2, default=str)
            os.replace(tmp, self._agents_file)
        except Exception:
            logger.exception("Failed to save agent registry")

    def set_agent_quota(self, org_id: str, limit: float, unit: str = "agents",
                         workspace_id: Optional[str] = None,
                         period: QuotaPeriod = QuotaPeriod.MONTHLY) -> ResourceQuota:
        try:
            now = datetime.now(timezone.utc).isoformat()
            qid = str(uuid.uuid4())
            quota = ResourceQuota(
                id=qid, org_id=org_id, workspace_id=workspace_id, project_id=None,
                quota_type=QuotaType.AGENTS, period=period, limit=limit, used=0.0,
                remaining=limit, unit=unit, status=QuotaStatus.ACTIVE, reset_at=now,
                created_at=now, updated_at=now,
            )
            self._quotas[qid] = quota
            self._save()
            self.telemetry["agent_quotas_set"] += 1
            logger.info("Set agent quota %s for org %s limit %f", qid, org_id, limit)
            return quota
        except Exception:
            logger.exception("Failed to set agent quota")
            raise

    def get_agent_quota(self, quota_id: str) -> ResourceQuota:
        quota = self._quotas.get(quota_id)
        if quota is None:
            raise ValueError(f"Agent quota not found: {quota_id}")
        self.telemetry["agent_quotas_read"] += 1
        return quota

    def track_agent_usage(self, quota_id: str, count: float = 1.0) -> ResourceQuota:
        try:
            quota = self.get_agent_quota(quota_id)
            quota.used += count
            quota.remaining = max(0, quota.limit - quota.used)
            usage_pct = (quota.used / quota.limit * 100) if quota.limit > 0 else 0
            if usage_pct >= 100:
                quota.status = QuotaStatus.EXCEEDED
            elif usage_pct >= 80:
                quota.status = QuotaStatus.NEARING_LIMIT
            quota.updated_at = datetime.now(timezone.utc).isoformat()
            self._quotas[quota_id] = quota
            self._save()
            self.telemetry["agent_usage_tracked"] += 1
            return quota
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to track agent usage for %s", quota_id)
            raise

    def check_agent_quota(self, quota_id: str) -> dict:
        try:
            quota = self.get_agent_quota(quota_id)
            usage_pct = (quota.used / quota.limit * 100) if quota.limit > 0 else 0
            quota.remaining = max(0, quota.limit - quota.used)
            if usage_pct >= 100:
                quota.status = QuotaStatus.EXCEEDED
            elif usage_pct >= 80:
                quota.status = QuotaStatus.NEARING_LIMIT
            else:
                quota.status = QuotaStatus.ACTIVE
            quota.updated_at = datetime.now(timezone.utc).isoformat()
            self._quotas[quota_id] = quota
            self._save()
            self.telemetry["agent_quotas_checked"] += 1
            return {
                "quota_id": quota_id, "allowed": usage_pct < 100,
                "used": quota.used, "limit": quota.limit,
                "remaining": quota.remaining, "usage_percent": round(usage_pct, 2),
                "status": quota.status.value,
            }
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to check agent quota %s", quota_id)
            raise

    def list_active_agents(self, org_id: Optional[str] = None) -> list[dict]:
        try:
            agents = list(self._agents.values())
            if org_id:
                agents = [a for a in agents if a.get("org_id") == org_id]
            self.telemetry["active_agents_listed"] += 1
            return agents
        except Exception:
            logger.exception("Failed to list active agents")
            raise


class WorkerQuotaManager:
    """Manages worker quotas with JSON persistence."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._quotas_file = os.path.join(storage_dir, "worker_quotas.json")
        self._quotas: dict[str, ResourceQuota] = {}
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self._quotas_file):
                with open(self._quotas_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._quotas = {k: ResourceQuota.from_dict(v) for k, v in data.items()}
                logger.info("Loaded %d worker quotas", len(self._quotas))
        except Exception:
            logger.exception("Failed to load worker quotas; starting fresh")
            self._quotas = {}

    def _save(self) -> None:
        try:
            data = {k: v.to_dict() for k, v in self._quotas.items()}
            tmp = self._quotas_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._quotas_file)
        except Exception:
            logger.exception("Failed to save worker quotas")

    def set_worker_quota(self, org_id: str, limit: float, unit: str = "workers",
                          workspace_id: Optional[str] = None,
                          period: QuotaPeriod = QuotaPeriod.MONTHLY) -> ResourceQuota:
        try:
            now = datetime.now(timezone.utc).isoformat()
            qid = str(uuid.uuid4())
            quota = ResourceQuota(
                id=qid, org_id=org_id, workspace_id=workspace_id, project_id=None,
                quota_type=QuotaType.WORKERS, period=period, limit=limit, used=0.0,
                remaining=limit, unit=unit, status=QuotaStatus.ACTIVE, reset_at=now,
                created_at=now, updated_at=now,
            )
            self._quotas[qid] = quota
            self._save()
            self.telemetry["worker_quotas_set"] += 1
            logger.info("Set worker quota %s for org %s limit %f", qid, org_id, limit)
            return quota
        except Exception:
            logger.exception("Failed to set worker quota")
            raise

    def get_worker_quota(self, quota_id: str) -> ResourceQuota:
        quota = self._quotas.get(quota_id)
        if quota is None:
            raise ValueError(f"Worker quota not found: {quota_id}")
        self.telemetry["worker_quotas_read"] += 1
        return quota

    def track_worker_usage(self, quota_id: str, count: float = 1.0) -> ResourceQuota:
        try:
            quota = self.get_worker_quota(quota_id)
            quota.used += count
            quota.remaining = max(0, quota.limit - quota.used)
            usage_pct = (quota.used / quota.limit * 100) if quota.limit > 0 else 0
            if usage_pct >= 100:
                quota.status = QuotaStatus.EXCEEDED
            elif usage_pct >= 80:
                quota.status = QuotaStatus.NEARING_LIMIT
            quota.updated_at = datetime.now(timezone.utc).isoformat()
            self._quotas[quota_id] = quota
            self._save()
            self.telemetry["worker_usage_tracked"] += 1
            return quota
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to track worker usage for %s", quota_id)
            raise

    def check_worker_quota(self, quota_id: str) -> dict:
        try:
            quota = self.get_worker_quota(quota_id)
            usage_pct = (quota.used / quota.limit * 100) if quota.limit > 0 else 0
            quota.remaining = max(0, quota.limit - quota.used)
            if usage_pct >= 100:
                quota.status = QuotaStatus.EXCEEDED
            elif usage_pct >= 80:
                quota.status = QuotaStatus.NEARING_LIMIT
            else:
                quota.status = QuotaStatus.ACTIVE
            quota.updated_at = datetime.now(timezone.utc).isoformat()
            self._quotas[quota_id] = quota
            self._save()
            self.telemetry["worker_quotas_checked"] += 1
            return {
                "quota_id": quota_id, "allowed": usage_pct < 100,
                "used": quota.used, "limit": quota.limit,
                "remaining": quota.remaining, "usage_percent": round(usage_pct, 2),
                "status": quota.status.value,
            }
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to check worker quota %s", quota_id)
            raise


class QuotaAlertManager:
    """Manages quota alerts with JSON persistence."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._alerts_file = os.path.join(storage_dir, "quota_alerts.json")
        self._alerts: dict[str, QuotaAlert] = {}
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self._alerts_file):
                with open(self._alerts_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._alerts = {k: QuotaAlert.from_dict(v) for k, v in data.items()}
                logger.info("Loaded %d quota alerts", len(self._alerts))
        except Exception:
            logger.exception("Failed to load quota alerts; starting fresh")
            self._alerts = {}

    def _save(self) -> None:
        try:
            data = {k: v.to_dict() for k, v in self._alerts.items()}
            tmp = self._alerts_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._alerts_file)
        except Exception:
            logger.exception("Failed to save quota alerts")

    def create_alert(self, quota_id: str, quota_type: QuotaType, threshold: float,
                      current_usage: float, message: str,
                      severity: str = "warning") -> QuotaAlert:
        try:
            now = datetime.now(timezone.utc).isoformat()
            alert = QuotaAlert(
                id=str(uuid.uuid4()), quota_id=quota_id, quota_type=quota_type,
                threshold=threshold, current_usage=current_usage, message=message,
                created_at=now, acknowledged=False, severity=severity,
            )
            self._alerts[alert.id] = alert
            self._save()
            self.telemetry["alerts_created"] += 1
            logger.info("Created alert %s for quota %s (threshold %f)", alert.id, quota_id, threshold)
            return alert
        except Exception:
            logger.exception("Failed to create alert")
            raise

    def get_alerts(self, quota_id: Optional[str] = None,
                    acknowledged: Optional[bool] = None) -> list[QuotaAlert]:
        try:
            results = list(self._alerts.values())
            if quota_id is not None:
                results = [a for a in results if a.quota_id == quota_id]
            if acknowledged is not None:
                results = [a for a in results if a.acknowledged == acknowledged]
            results.sort(key=lambda x: x.created_at, reverse=True)
            self.telemetry["alerts_read"] += 1
            return results
        except Exception:
            logger.exception("Failed to get alerts")
            raise

    def acknowledge_alert(self, alert_id: str) -> QuotaAlert:
        try:
            alert = self._alerts.get(alert_id)
            if alert is None:
                raise ValueError(f"Alert not found: {alert_id}")
            alert.acknowledged = True
            self._alerts[alert_id] = alert
            self._save()
            self.telemetry["alerts_acknowledged"] += 1
            logger.info("Acknowledged alert %s", alert_id)
            return alert
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to acknowledge alert %s", alert_id)
            raise

    def check_thresholds(self, quota_id: str, current_usage: float, limit: float) -> list[QuotaAlert]:
        try:
            alerts = []
            thresholds = [50, 75, 90, 95, 100]
            for t in thresholds:
                if limit > 0 and current_usage >= (limit * t / 100):
                    existing = [a for a in self._alerts.values()
                                if a.quota_id == quota_id and a.threshold == t
                                and not a.acknowledged]
                    if not existing:
                        alert = self.create_alert(
                            quota_id=quota_id, quota_type=QuotaType.REPOSITORY,
                            threshold=t, current_usage=current_usage,
                            message=f"Quota usage at {t}% ({current_usage}/{limit})",
                            severity="critical" if t >= 90 else "warning",
                        )
                        alerts.append(alert)
            self.telemetry["thresholds_checked"] += 1
            return alerts
        except Exception:
            logger.exception("Failed to check thresholds for %s", quota_id)
            raise

    def auto_generate_alerts(self, quotas: list[ResourceQuota]) -> list[QuotaAlert]:
        try:
            alerts = []
            for quota in quotas:
                pct = (quota.used / quota.limit * 100) if quota.limit > 0 else 0
                thresholds = self.check_thresholds(quota.id, quota.used, quota.limit)
                alerts.extend(thresholds)
            self.telemetry["auto_alerts_generated"] += len(alerts)
            return alerts
        except Exception:
            logger.exception("Failed to auto-generate alerts")
            raise


class BillingManager:
    """Manages billing metrics with JSON persistence."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._metrics_file = os.path.join(storage_dir, "billing_metrics.json")
        self._metrics: dict[str, BillingMetric] = {}
        self._invoices_file = os.path.join(storage_dir, "invoices.json")
        self._invoices: dict[str, dict] = {}
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self._metrics_file):
                with open(self._metrics_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._metrics = {k: BillingMetric.from_dict(v) for k, v in data.items()}
                logger.info("Loaded %d billing metrics", len(self._metrics))
        except Exception:
            logger.exception("Failed to load billing metrics; starting fresh")
            self._metrics = {}
        try:
            if os.path.exists(self._invoices_file):
                with open(self._invoices_file, "r", encoding="utf-8") as fh:
                    self._invoices = json.load(fh)
        except Exception:
            self._invoices = {}

    def _save(self) -> None:
        try:
            data = {k: v.to_dict() for k, v in self._metrics.items()}
            tmp = self._metrics_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._metrics_file)
        except Exception:
            logger.exception("Failed to save billing metrics")
        try:
            tmp = self._invoices_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._invoices, fh, indent=2, default=str)
            os.replace(tmp, self._invoices_file)
        except Exception:
            logger.exception("Failed to save invoices")

    def track_metric(self, org_id: str, metric_type: str, quantity: float,
                      unit: str, rate: float, period: str = "") -> BillingMetric:
        try:
            now = datetime.now(timezone.utc).isoformat()
            cost = quantity * rate
            metric = BillingMetric(
                id=str(uuid.uuid4()), org_id=org_id, metric_type=metric_type,
                quantity=quantity, unit=unit, rate=rate, cost=cost,
                timestamp=now, period=period,
            )
            self._metrics[metric.id] = metric
            self._save()
            self.telemetry["billing_metrics_tracked"] += 1
            logger.info("Tracked billing metric %s for org %s cost %f", metric.id, org_id, cost)
            return metric
        except Exception:
            logger.exception("Failed to track billing metric")
            raise

    def get_usage(self, org_id: str, metric_type: Optional[str] = None,
                   start_date: Optional[str] = None,
                   end_date: Optional[str] = None) -> list[BillingMetric]:
        try:
            results = [m for m in self._metrics.values() if m.org_id == org_id]
            if metric_type is not None:
                results = [m for m in results if m.metric_type == metric_type]
            if start_date is not None:
                results = [m for m in results if m.timestamp >= start_date]
            if end_date is not None:
                results = [m for m in results if m.timestamp <= end_date]
            results.sort(key=lambda x: x.timestamp, reverse=True)
            self.telemetry["billing_usage_read"] += 1
            return results
        except Exception:
            logger.exception("Failed to get billing usage")
            raise

    def calculate_cost(self, org_id: str, metric_type: Optional[str] = None) -> dict:
        try:
            metrics = self.get_usage(org_id, metric_type=metric_type)
            total_cost = sum(m.cost for m in metrics)
            total_quantity = sum(m.quantity for m in metrics)
            by_type = defaultdict(float)
            for m in metrics:
                by_type[m.metric_type] += m.cost
            result = {
                "org_id": org_id, "total_cost": round(total_cost, 4),
                "total_quantity": total_quantity, "metric_count": len(metrics),
                "cost_by_type": dict(by_type),
            }
            self.telemetry["costs_calculated"] += 1
            return result
        except Exception:
            logger.exception("Failed to calculate cost for org %s", org_id)
            raise

    def generate_invoice(self, org_id: str, period: str) -> dict:
        try:
            metrics = self.get_usage(org_id)
            period_metrics = [m for m in metrics if m.period == period or not m.period]
            total = sum(m.cost for m in period_metrics)
            by_type = defaultdict(float)
            for m in period_metrics:
                by_type[m.metric_type] += m.cost
            invoice = {
                "invoice_id": str(uuid.uuid4()),
                "org_id": org_id,
                "period": period,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "total_cost": round(total, 4),
                "metric_count": len(period_metrics),
                "breakdown": dict(by_type),
                "status": "pending",
            }
            self._invoices[invoice["invoice_id"]] = invoice
            self._save()
            self.telemetry["invoices_generated"] += 1
            logger.info("Generated invoice %s for org %s period %s total %f",
                        invoice["invoice_id"], org_id, period, total)
            return invoice
        except Exception:
            logger.exception("Failed to generate invoice for org %s", org_id)
            raise

    def get_org_billing(self, org_id: str) -> dict:
        try:
            metrics = self.get_usage(org_id)
            total_cost = sum(m.cost for m in metrics)
            by_type = defaultdict(lambda: {"quantity": 0, "cost": 0})
            for m in metrics:
                by_type[m.metric_type]["quantity"] += m.quantity
                by_type[m.metric_type]["cost"] += m.cost
            org_invoices = [v for v in self._invoices.values() if v.get("org_id") == org_id]
            return {
                "org_id": org_id,
                "total_cost": round(total_cost, 4),
                "total_metrics": len(metrics),
                "breakdown": dict(by_type),
                "invoices": org_invoices,
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }
        except Exception:
            logger.exception("Failed to get org billing for %s", org_id)
            raise


class ResourceManager(RepositoryQuotaManager, StorageQuotaManager, TokenQuotaManager,
                       EmbeddingQuotaManager, AgentQuotaManager, WorkerQuotaManager,
                       QuotaAlertManager, BillingManager):
    """Unified resource manager combining all quota and billing management."""

    def __init__(self, storage_dir: str):
        RepositoryQuotaManager.__init__(self, storage_dir)
        StorageQuotaManager.__init__(self, storage_dir)
        TokenQuotaManager.__init__(self, storage_dir)
        EmbeddingQuotaManager.__init__(self, storage_dir)
        AgentQuotaManager.__init__(self, storage_dir)
        WorkerQuotaManager.__init__(self, storage_dir)
        QuotaAlertManager.__init__(self, storage_dir)
        BillingManager.__init__(self, storage_dir)
        self.telemetry: dict = defaultdict(int)
        logger.info("ResourceManager initialized at %s", storage_dir)

    def check_all_quotas(self, org_id: str) -> dict:
        try:
            all_quotas = (
                list(self._quotas.values())
            )
            org_quotas = [q for q in all_quotas if q.org_id == org_id]
            results = {}
            for q in org_quotas:
                try:
                    qt = q.quota_type.value
                    if qt not in results:
                        results[qt] = {"active": 0, "nearing": 0, "exceeded": 0, "total": 0}
                    results[qt]["total"] += 1
                    if q.status == QuotaStatus.ACTIVE:
                        results[qt]["active"] += 1
                    elif q.status == QuotaStatus.NEARING_LIMIT:
                        results[qt]["nearing"] += 1
                    elif q.status == QuotaStatus.EXCEEDED:
                        results[qt]["exceeded"] += 1
                except Exception:
                    continue
            self.telemetry["all_quotas_checked"] += 1
            return {
                "org_id": org_id,
                "results": results,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception:
            logger.exception("Failed to check all quotas for org %s", org_id)
            raise

    def get_org_quota_report(self, org_id: str) -> dict:
        try:
            repo_report = self.get_usage_report(org_id)
            storage_report = self.get_storage_report(org_id)
            token_report = self.get_token_usage_report(org_id)
            billing = self.get_org_billing(org_id)
            report = {
                "org_id": org_id,
                "repository_quotas": repo_report,
                "storage_quotas": storage_report,
                "token_quotas": token_report,
                "billing": billing,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
            self.telemetry["org_reports_generated"] += 1
            return report
        except Exception:
            logger.exception("Failed to generate org quota report for %s", org_id)
            raise

    def get_workspace_quota_report(self, org_id: str, workspace_id: str) -> dict:
        try:
            repo_quotas = [q for q in self._quotas.values()
                           if q.org_id == org_id and q.workspace_id == workspace_id]
            storage_quotas = [q for q in self._quotas.values()
                              if q.org_id == org_id and q.workspace_id == workspace_id]
            token_quotas = [q for q in self._quotas.values()
                            if q.org_id == org_id and q.workspace_id == workspace_id]
            report = {
                "org_id": org_id,
                "workspace_id": workspace_id,
                "repository_quotas": [q.to_dict() for q in repo_quotas],
                "storage_quotas": [q.to_dict() for q in storage_quotas],
                "token_quotas": [q.to_dict() for q in token_quotas],
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
            self.telemetry["workspace_reports_generated"] += 1
            return report
        except Exception:
            logger.exception("Failed to generate workspace quota report")
            raise
