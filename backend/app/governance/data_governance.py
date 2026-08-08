import json
import uuid
import os
import logging
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


class DataClassification(Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"
    REGULATED = "regulated"


class DataCategory(Enum):
    USER_DATA = "user_data"
    FINANCIAL = "financial"
    HEALTH = "health"
    PII = "pii"
    CODE = "code"
    CONFIGURATION = "configuration"
    LOGS = "logs"
    METRICS = "metrics"
    DOCUMENTS = "documents"
    AI_MODEL = "ai_model"
    PROMPT = "prompt"
    AUDIT = "audit"


class RetentionAction(Enum):
    DELETE = "delete"
    ARCHIVE = "archive"
    ANONYMIZE = "anonymize"
    EXPORT = "export"
    TRANSFER = "transfer"


class DataState(Enum):
    CREATED = "created"
    STORED = "stored"
    PROCESSED = "processed"
    TRANSFERRED = "transferred"
    ARCHIVED = "archived"
    DELETED = "deleted"
    RESTORED = "restored"


@dataclass
class DataAsset:
    id: str
    org_id: str
    name: str
    description: str = ""
    category: DataCategory = DataCategory.CONFIGURATION
    classification: DataClassification = DataClassification.INTERNAL
    owner: str = ""
    location: str = ""
    format: str = ""
    size_bytes: int = 0
    retention_days: int = 365
    retention_action: RetentionAction = RetentionAction.DELETE
    tags: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["category"] = self.category.value
        d["classification"] = self.classification.value
        d["retention_action"] = self.retention_action.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "DataAsset":
        data["category"] = DataCategory(data["category"])
        data["classification"] = DataClassification(data["classification"])
        data["retention_action"] = RetentionAction(data["retention_action"])
        return cls(**data)


@dataclass
class DataLineageEntry:
    id: str
    asset_id: str
    source_asset_id: str = ""
    transformation: str = ""
    state: DataState = DataState.CREATED
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    actor: str = ""
    description: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["state"] = self.state.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "DataLineageEntry":
        data["state"] = DataState(data["state"])
        return cls(**data)


@dataclass
class DataRetentionPolicy:
    id: str
    org_id: str
    name: str
    category: DataCategory = DataCategory.CONFIGURATION
    classification: DataClassification = DataClassification.INTERNAL
    retention_days: int = 365
    action: RetentionAction = RetentionAction.DELETE
    exempt_assets: list = field(default_factory=list)
    enabled: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["category"] = self.category.value
        d["classification"] = self.classification.value
        d["action"] = self.action.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "DataRetentionPolicy":
        data["category"] = DataCategory(data["category"])
        data["classification"] = DataClassification(data["classification"])
        data["action"] = RetentionAction(data["action"])
        return cls(**data)


@dataclass
class DataAccessRequest:
    id: str
    org_id: str
    asset_id: str
    requester: str
    reason: str = ""
    access_type: str = "read"
    requested_duration_hours: int = 24
    status: str = "pending"
    approved_by: str = ""
    approved_at: Optional[str] = None
    expires_at: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DataAccessRequest":
        return cls(**data)


@dataclass
class DataGovernanceReport:
    id: str
    org_id: str
    period_start: str
    period_end: str
    total_assets: int = 0
    by_classification: dict = field(default_factory=dict)
    by_category: dict = field(default_factory=dict)
    total_storage_bytes: int = 0
    assets_expiring: int = 0
    access_requests: int = 0
    compliance_score: float = 0.0
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DataGovernanceReport":
        return cls(**data)


class DataGovernanceManager:
    def __init__(self, storage_dir: str = "data_governance_data"):
        self.storage_dir = storage_dir
        self._assets: dict[str, DataAsset] = {}
        self._lineage: dict[str, list[DataLineageEntry]] = defaultdict(list)
        self._retention_policies: dict[str, DataRetentionPolicy] = {}
        self._access_requests: dict[str, DataAccessRequest] = {}
        self._reports: dict[str, DataGovernanceReport] = {}
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _assets_path(self) -> str:
        return os.path.join(self.storage_dir, "assets.json")

    def _lineage_path(self) -> str:
        return os.path.join(self.storage_dir, "lineage.json")

    def _retention_path(self) -> str:
        return os.path.join(self.storage_dir, "retention_policies.json")

    def _access_requests_path(self) -> str:
        return os.path.join(self.storage_dir, "access_requests.json")

    def _reports_path(self) -> str:
        return os.path.join(self.storage_dir, "reports.json")

    def _save(self) -> None:
        try:
            assets_data = {aid: a.to_dict() for aid, a in self._assets.items()}
            with open(self._assets_path(), "w", encoding="utf-8") as f:
                json.dump(assets_data, f, indent=2, default=str)

            lineage_data = {aid: [e.to_dict() for e in entries] for aid, entries in self._lineage.items()}
            with open(self._lineage_path(), "w", encoding="utf-8") as f:
                json.dump(lineage_data, f, indent=2, default=str)

            retention_data = {pid: p.to_dict() for pid, p in self._retention_policies.items()}
            with open(self._retention_path(), "w", encoding="utf-8") as f:
                json.dump(retention_data, f, indent=2, default=str)

            access_data = {rid: r.to_dict() for rid, r in self._access_requests.items()}
            with open(self._access_requests_path(), "w", encoding="utf-8") as f:
                json.dump(access_data, f, indent=2, default=str)

            reports_data = {rid: r.to_dict() for rid, r in self._reports.items()}
            with open(self._reports_path(), "w", encoding="utf-8") as f:
                json.dump(reports_data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save data governance data: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._assets_path()):
                with open(self._assets_path(), "r", encoding="utf-8") as f:
                    assets_data = json.load(f)
                for aid, data in assets_data.items():
                    try:
                        self._assets[aid] = DataAsset.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed asset %s: %s", aid, e)

            if os.path.exists(self._lineage_path()):
                with open(self._lineage_path(), "r", encoding="utf-8") as f:
                    lineage_data = json.load(f)
                for aid, entries in lineage_data.items():
                    self._lineage[aid] = []
                    for edata in entries:
                        try:
                            self._lineage[aid].append(DataLineageEntry.from_dict(edata))
                        except Exception as e:
                            logger.warning("Skipping malformed lineage entry for asset %s: %s", aid, e)

            if os.path.exists(self._retention_path()):
                with open(self._retention_path(), "r", encoding="utf-8") as f:
                    retention_data = json.load(f)
                for pid, data in retention_data.items():
                    try:
                        self._retention_policies[pid] = DataRetentionPolicy.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed retention policy %s: %s", pid, e)

            if os.path.exists(self._access_requests_path()):
                with open(self._access_requests_path(), "r", encoding="utf-8") as f:
                    access_data = json.load(f)
                for rid, data in access_data.items():
                    try:
                        self._access_requests[rid] = DataAccessRequest.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed access request %s: %s", rid, e)

            if os.path.exists(self._reports_path()):
                with open(self._reports_path(), "r", encoding="utf-8") as f:
                    reports_data = json.load(f)
                for rid, data in reports_data.items():
                    try:
                        self._reports[rid] = DataGovernanceReport.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed report %s: %s", rid, e)
        except Exception as e:
            logger.error("Failed to load data governance data: %s", e, exc_info=True)

    def register_asset(self, asset: DataAsset) -> DataAsset:
        self._telemetry["register_asset_calls"] += 1
        if asset.id in self._assets:
            raise ValueError(f"DataAsset with id '{asset.id}' already exists.")
        now = datetime.now(timezone.utc).isoformat()
        asset.created_at = now
        asset.updated_at = now
        self._assets[asset.id] = asset

        lineage_entry = DataLineageEntry(
            id=str(uuid.uuid4()),
            asset_id=asset.id,
            state=DataState.CREATED,
            actor=asset.owner,
            description=f"Asset '{asset.name}' registered",
        )
        self._lineage[asset.id].append(lineage_entry)
        self._save()
        logger.info("Registered data asset: %s (%s)", asset.name, asset.id)
        return asset

    def get_asset(self, asset_id: str) -> Optional[DataAsset]:
        self._telemetry["get_asset_calls"] += 1
        return self._assets.get(asset_id)

    def update_asset(self, asset_id: str, updates: dict) -> Optional[DataAsset]:
        self._telemetry["update_asset_calls"] += 1
        asset = self._assets.get(asset_id)
        if not asset:
            logger.warning("Attempted to update unknown asset: %s", asset_id)
            return None
        for key, value in updates.items():
            if hasattr(asset, key) and key not in ("id", "org_id", "created_at"):
                if key == "category":
                    setattr(asset, key, DataCategory(value) if isinstance(value, str) else value)
                elif key == "classification":
                    setattr(asset, key, DataClassification(value) if isinstance(value, str) else value)
                elif key == "retention_action":
                    setattr(asset, key, RetentionAction(value) if isinstance(value, str) else value)
                else:
                    setattr(asset, key, value)
        asset.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        logger.info("Updated data asset: %s", asset_id)
        return asset

    def list_assets(self, org_id: str, category: Optional[DataCategory] = None, classification: Optional[DataClassification] = None) -> list[DataAsset]:
        self._telemetry["list_assets_calls"] += 1
        results = [a for a in self._assets.values() if a.org_id == org_id]
        if category:
            results = [a for a in results if a.category == category]
        if classification:
            results = [a for a in results if a.classification == classification]
        return results

    def record_lineage(self, entry: DataLineageEntry) -> DataLineageEntry:
        self._telemetry["record_lineage_calls"] += 1
        self._lineage[entry.asset_id].append(entry)
        self._save()
        logger.info("Recorded lineage entry for asset %s", entry.asset_id)
        return entry

    def get_asset_lineage(self, asset_id: str) -> list[DataLineageEntry]:
        self._telemetry["get_asset_lineage_calls"] += 1
        return list(self._lineage.get(asset_id, []))

    def trace_lineage(self, asset_id: str) -> list[dict]:
        self._telemetry["trace_lineage_calls"] += 1
        visited = set()
        chain = []

        def _trace(aid: str, depth: int = 0):
            if aid in visited or depth > 50:
                return
            visited.add(aid)
            entries = self._lineage.get(aid, [])
            for entry in entries:
                chain.append({
                    "asset_id": entry.asset_id,
                    "source_asset_id": entry.source_asset_id,
                    "transformation": entry.transformation,
                    "state": entry.state.value,
                    "timestamp": entry.timestamp,
                    "actor": entry.actor,
                    "description": entry.description,
                })
                if entry.source_asset_id:
                    _trace(entry.source_asset_id, depth + 1)

        _trace(asset_id)
        return chain

    def create_retention_policy(self, policy: DataRetentionPolicy) -> DataRetentionPolicy:
        self._telemetry["create_retention_policy_calls"] += 1
        if policy.id in self._retention_policies:
            raise ValueError(f"DataRetentionPolicy with id '{policy.id}' already exists.")
        now = datetime.now(timezone.utc).isoformat()
        policy.created_at = now
        policy.updated_at = now
        self._retention_policies[policy.id] = policy
        self._save()
        logger.info("Created retention policy: %s (%s)", policy.name, policy.id)
        return policy

    def apply_retention_policies(self, org_id: str) -> list[dict]:
        self._telemetry["apply_retention_policies_calls"] += 1
        results = []
        policies = [p for p in self._retention_policies.values() if p.org_id == org_id and p.enabled]
        assets = [a for a in self._assets.values() if a.org_id == org_id]
        now = datetime.now(timezone.utc)

        for asset in assets:
            for policy in policies:
                if asset.id in policy.exempt_assets:
                    continue
                if policy.category != asset.category:
                    continue
                if policy.classification != asset.classification:
                    continue
                created = datetime.fromisoformat(asset.created_at)
                age_days = (now - created).days
                if age_days >= policy.retention_days:
                    action = policy.action
                    lineage_entry = DataLineageEntry(
                        id=str(uuid.uuid4()),
                        asset_id=asset.id,
                        state=DataState.ARCHIVED if action == RetentionAction.ARCHIVE else
                              DataState.DELETED if action == RetentionAction.DELETE else
                              DataState.PROCESSED,
                        actor="retention_policy",
                        description=f"Retention policy '{policy.name}' applied: {action.value} after {age_days} days",
                    )
                    self._lineage[asset.id].append(lineage_entry)
                    results.append({
                        "asset_id": asset.id,
                        "asset_name": asset.name,
                        "policy_id": policy.id,
                        "policy_name": policy.name,
                        "action": action.value,
                        "age_days": age_days,
                        "retention_days": policy.retention_days,
                    })
                    logger.info("Retention applied to %s: %s (age=%d, limit=%d)", asset.id, action.value, age_days, policy.retention_days)

        if results:
            self._save()
        return results

    def create_access_request(self, request: DataAccessRequest) -> DataAccessRequest:
        self._telemetry["create_access_request_calls"] += 1
        if request.id in self._access_requests:
            raise ValueError(f"DataAccessRequest with id '{request.id}' already exists.")
        request.created_at = datetime.now(timezone.utc).isoformat()
        self._access_requests[request.id] = request
        self._save()
        logger.info("Created access request: %s by %s for asset %s", request.id, request.requester, request.asset_id)
        return request

    def approve_access_request(self, request_id: str, approver: str) -> Optional[DataAccessRequest]:
        self._telemetry["approve_access_request_calls"] += 1
        request = self._access_requests.get(request_id)
        if not request:
            logger.warning("Access request not found: %s", request_id)
            return None
        now = datetime.now(timezone.utc)
        request.status = "approved"
        request.approved_by = approver
        request.approved_at = now.isoformat()
        request.expires_at = (now + timedelta(hours=request.requested_duration_hours)).isoformat()
        self._save()
        logger.info("Approved access request %s by %s", request_id, approver)
        return request

    def get_data_governance_report(self, org_id: str, start_date: str, end_date: str) -> DataGovernanceReport:
        self._telemetry["get_data_governance_report_calls"] += 1
        assets = [a for a in self._assets.values() if a.org_id == org_id]
        total_assets = len(assets)
        total_storage_bytes = sum(a.size_bytes for a in assets)

        by_classification = defaultdict(int)
        by_category = defaultdict(int)
        for a in assets:
            by_classification[a.classification.value] += 1
            by_category[a.category.value] += 1

        now = datetime.now(timezone.utc)
        assets_expiring = 0
        for a in assets:
            created = datetime.fromisoformat(a.created_at)
            age_days = (now - created).days
            if age_days >= a.retention_days:
                assets_expiring += 1

        access_requests = len([r for r in self._access_requests.values() if r.org_id == org_id])
        total_possible = total_assets * 4 if total_assets > 0 else 1
        classified = sum(1 for a in assets if a.classification != DataClassification.INTERNAL)
        tracked = sum(1 for a in assets if len(self._lineage.get(a.id, [])) > 0)
        policy_hit = sum(1 for r in self._access_requests.values() if r.org_id == org_id and r.status == "approved")
        compliance_score = round((classified + tracked + policy_hit) / total_possible * 100, 2) if total_possible > 1 else 100.0

        report = DataGovernanceReport(
            id=str(uuid.uuid4()),
            org_id=org_id,
            period_start=start_date,
            period_end=end_date,
            total_assets=total_assets,
            by_classification=dict(by_classification),
            by_category=dict(by_category),
            total_storage_bytes=total_storage_bytes,
            assets_expiring=assets_expiring,
            access_requests=access_requests,
            compliance_score=compliance_score,
        )
        self._reports[report.id] = report
        self._save()
        logger.info("Generated data governance report for org %s", org_id)
        return report

    def classify_asset(self, asset_id: str, classification: DataClassification) -> Optional[DataAsset]:
        self._telemetry["classify_asset_calls"] += 1
        asset = self._assets.get(asset_id)
        if not asset:
            logger.warning("Attempted to classify unknown asset: %s", asset_id)
            return None
        old_classification = asset.classification
        asset.classification = classification
        asset.updated_at = datetime.now(timezone.utc).isoformat()

        lineage_entry = DataLineageEntry(
            id=str(uuid.uuid4()),
            asset_id=asset_id,
            state=DataState.PROCESSED,
            actor="governance_manager",
            description=f"Classification changed from {old_classification.value} to {classification.value}",
            metadata={"old_classification": old_classification.value, "new_classification": classification.value},
        )
        self._lineage[asset_id].append(lineage_entry)
        self._save()
        logger.info("Reclassified asset %s: %s -> %s", asset_id, old_classification.value, classification.value)
        return asset

    def get_telemetry(self) -> dict:
        return dict(self._telemetry)
