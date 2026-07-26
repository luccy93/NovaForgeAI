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


class ChangeEntity(Enum):
    REPOSITORY = "repository"
    CONFIGURATION = "configuration"
    PROMPT = "prompt"
    MODEL = "model"
    POLICY = "policy"
    DEPLOYMENT = "deployment"
    PERMISSION = "permission"
    INTEGRATION = "integration"
    WORKSPACE = "workspace"
    ORGANIZATION = "organization"
    SECURITY_RULE = "security_rule"
    BILLING_PLAN = "billing_plan"


class ChangeType(Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    ENABLE = "enable"
    DISABLE = "disable"
    PROMOTE = "promote"
    ROLLBACK = "rollback"
    ARCHIVE = "archive"
    RESTORE = "restore"
    TRANSFER = "transfer"
    MERGE = "merge"
    SPLIT = "split"


class ChangeSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class ChangeStatus(Enum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    CANCELLED = "cancelled"


class ChangeSource(Enum):
    MANUAL = "manual"
    API = "api"
    AUTOMATION = "automation"
    SCHEDULED = "scheduled"
    CI_CD = "ci_cd"
    POLICY_ENFORCEMENT = "policy_enforcement"
    SYSTEM = "system"


@dataclass
class ChangeRecord:
    id: str
    org_id: str
    workspace_id: str
    entity: ChangeEntity
    entity_id: str
    change_type: ChangeType
    severity: ChangeSeverity
    status: ChangeStatus
    source: ChangeSource
    title: str
    description: str = ""
    before_snapshot: dict = field(default_factory=dict)
    after_snapshot: dict = field(default_factory=dict)
    diff_summary: str = ""
    initiated_by: str = ""
    approved_by: str = ""
    approved_at: Optional[str] = None
    performed_at: Optional[str] = None
    completed_at: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["entity"] = self.entity.value
        d["change_type"] = self.change_type.value
        d["severity"] = self.severity.value
        d["status"] = self.status.value
        d["source"] = self.source.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ChangeRecord":
        data["entity"] = ChangeEntity(data["entity"])
        data["change_type"] = ChangeType(data["change_type"])
        data["severity"] = ChangeSeverity(data["severity"])
        data["status"] = ChangeStatus(data["status"])
        data["source"] = ChangeSource(data["source"])
        return cls(**data)


@dataclass
class ChangeRequest:
    id: str
    org_id: str
    title: str
    description: str = ""
    changes: list[ChangeRecord] = field(default_factory=list)
    reason: str = ""
    impact_analysis: str = ""
    rollback_plan: str = ""
    risk_assessment: str = ""
    status: ChangeStatus = ChangeStatus.PENDING_REVIEW
    severity: ChangeSeverity = ChangeSeverity.MEDIUM
    requester: str = ""
    reviewer: str = ""
    approver: str = ""
    submitted_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    reviewed_at: Optional[str] = None
    approved_at: Optional[str] = None
    completed_at: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["severity"] = self.severity.value
        d["changes"] = [c.to_dict() for c in self.changes]
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ChangeRequest":
        data["status"] = ChangeStatus(data["status"])
        data["severity"] = ChangeSeverity(data["severity"])
        data["changes"] = [ChangeRecord.from_dict(c) for c in data["changes"]]
        return cls(**data)


@dataclass
class ChangeWindow:
    id: str
    org_id: str
    name: str
    start_time: str
    end_time: str
    allowed_change_types: list[ChangeType] = field(default_factory=list)
    max_severity: ChangeSeverity = ChangeSeverity.HIGH
    is_active: bool = True
    created_by: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["allowed_change_types"] = [t.value for t in self.allowed_change_types]
        d["max_severity"] = self.max_severity.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ChangeWindow":
        data["allowed_change_types"] = [ChangeType(t) for t in data["allowed_change_types"]]
        data["max_severity"] = ChangeSeverity(data["max_severity"])
        return cls(**data)


@dataclass
class ChangeNotification:
    id: str
    change_id: str
    recipient: str
    message: str = ""
    sent_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    read_at: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ChangeNotification":
        return cls(**data)


_severity_rank = {
    ChangeSeverity.LOW: 0,
    ChangeSeverity.MEDIUM: 1,
    ChangeSeverity.HIGH: 2,
    ChangeSeverity.CRITICAL: 3,
    ChangeSeverity.EMERGENCY: 4,
}


class ChangeManager:
    def __init__(self, storage_dir: str = "change_management_data"):
        self.storage_dir = storage_dir
        self._changes: dict[str, ChangeRecord] = {}
        self._requests: dict[str, ChangeRequest] = {}
        self._windows: dict[str, ChangeWindow] = {}
        self._notifications: list[ChangeNotification] = []
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _changes_path(self) -> str:
        return os.path.join(self.storage_dir, "changes.json")

    def _requests_path(self) -> str:
        return os.path.join(self.storage_dir, "requests.json")

    def _windows_path(self) -> str:
        return os.path.join(self.storage_dir, "windows.json")

    def _notifications_path(self) -> str:
        return os.path.join(self.storage_dir, "notifications.json")

    def _save(self) -> None:
        try:
            changes_data = {cid: c.to_dict() for cid, c in self._changes.items()}
            with open(self._changes_path(), "w", encoding="utf-8") as f:
                json.dump(changes_data, f, indent=2, default=str)

            requests_data = {rid: r.to_dict() for rid, r in self._requests.items()}
            with open(self._requests_path(), "w", encoding="utf-8") as f:
                json.dump(requests_data, f, indent=2, default=str)

            windows_data = {wid: w.to_dict() for wid, w in self._windows.items()}
            with open(self._windows_path(), "w", encoding="utf-8") as f:
                json.dump(windows_data, f, indent=2, default=str)

            notifications_data = [n.to_dict() for n in self._notifications]
            with open(self._notifications_path(), "w", encoding="utf-8") as f:
                json.dump(notifications_data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save change management data: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._changes_path()):
                with open(self._changes_path(), "r", encoding="utf-8") as f:
                    changes_data = json.load(f)
                for cid, data in changes_data.items():
                    try:
                        self._changes[cid] = ChangeRecord.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed change record %s: %s", cid, e)

            if os.path.exists(self._requests_path()):
                with open(self._requests_path(), "r", encoding="utf-8") as f:
                    requests_data = json.load(f)
                for rid, data in requests_data.items():
                    try:
                        self._requests[rid] = ChangeRequest.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed change request %s: %s", rid, e)

            if os.path.exists(self._windows_path()):
                with open(self._windows_path(), "r", encoding="utf-8") as f:
                    windows_data = json.load(f)
                for wid, data in windows_data.items():
                    try:
                        self._windows[wid] = ChangeWindow.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed change window %s: %s", wid, e)

            if os.path.exists(self._notifications_path()):
                with open(self._notifications_path(), "r", encoding="utf-8") as f:
                    notifications_data = json.load(f)
                for ndata in notifications_data:
                    try:
                        self._notifications.append(ChangeNotification.from_dict(ndata))
                    except Exception as e:
                        logger.warning("Skipping malformed notification: %s", e)
        except Exception as e:
            logger.error("Failed to load change management data: %s", e, exc_info=True)

    def _add_notification(self, change_id: str, recipient: str, message: str) -> None:
        notification = ChangeNotification(
            id=str(uuid.uuid4()),
            change_id=change_id,
            recipient=recipient,
            message=message,
        )
        self._notifications.append(notification)

    def record_change(self, record: ChangeRecord) -> ChangeRecord:
        self._telemetry["record_change_calls"] += 1
        if record.id in self._changes:
            raise ValueError(f"Change record with id '{record.id}' already exists.")
        now = datetime.now(timezone.utc).isoformat()
        record.created_at = now
        record.status = ChangeStatus.PENDING_REVIEW
        self._changes[record.id] = record
        self._save()
        logger.info("Recorded change: %s (%s)", record.title, record.id)
        return record

    def get_change(self, change_id: str) -> Optional[ChangeRecord]:
        self._telemetry["get_change_calls"] += 1
        return self._changes.get(change_id)

    def list_changes(self, org_id: str, entity: ChangeEntity = None, status: ChangeStatus = None, days: int = 90) -> list[ChangeRecord]:
        self._telemetry["list_changes_calls"] += 1
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        results = []
        for change in self._changes.values():
            if change.org_id != org_id:
                continue
            if entity and change.entity != entity:
                continue
            if status and change.status != status:
                continue
            try:
                created = datetime.fromisoformat(change.created_at)
                if created < cutoff:
                    continue
            except (ValueError, TypeError):
                pass
            results.append(change)
        return results

    def search_changes(self, query: str) -> list[ChangeRecord]:
        self._telemetry["search_changes_calls"] += 1
        q = query.lower()
        results = []
        for change in self._changes.values():
            if (q in change.title.lower() or q in change.description.lower() or
                q in change.id.lower() or q in change.entity_id.lower() or
                q in change.diff_summary.lower() or
                any(q in t.lower() for t in change.tags)):
                results.append(change)
        return results

    def create_change_request(self, request: ChangeRequest) -> ChangeRequest:
        self._telemetry["create_change_request_calls"] += 1
        if request.id in self._requests:
            raise ValueError(f"Change request with id '{request.id}' already exists.")
        now = datetime.now(timezone.utc).isoformat()
        request.submitted_at = now
        request.status = ChangeStatus.PENDING_REVIEW
        self._requests[request.id] = request

        for change in request.changes:
            if change.id in self._changes:
                self._changes[change.id].status = ChangeStatus.PENDING_REVIEW

        self._add_notification(
            request.id,
            request.requester,
            f"Change request '{request.title}' submitted for review",
        )
        self._save()
        logger.info("Created change request: %s (%s)", request.title, request.id)
        return request

    def approve_change_request(self, request_id: str, user: str) -> Optional[ChangeRequest]:
        self._telemetry["approve_change_request_calls"] += 1
        req = self._requests.get(request_id)
        if not req:
            logger.warning("Change request not found: %s", request_id)
            return None
        if req.status != ChangeStatus.PENDING_REVIEW:
            logger.warning("Change request %s is not pending review (status: %s)", request_id, req.status.value)
            return None
        now = datetime.now(timezone.utc).isoformat()
        req.status = ChangeStatus.APPROVED
        req.approver = user
        req.approved_at = now
        req.reviewed_at = now

        for change in req.changes:
            if change.id in self._changes:
                self._changes[change.id].status = ChangeStatus.APPROVED
                self._changes[change.id].approved_by = user
                self._changes[change.id].approved_at = now

        self._add_notification(
            request_id,
            req.requester,
            f"Change request '{req.title}' approved by {user}",
        )
        self._save()
        logger.info("Change request %s approved by %s", request_id, user)
        return req

    def reject_change_request(self, request_id: str, user: str, reason: str) -> Optional[ChangeRequest]:
        self._telemetry["reject_change_request_calls"] += 1
        req = self._requests.get(request_id)
        if not req:
            logger.warning("Change request not found: %s", request_id)
            return None
        if req.status != ChangeStatus.PENDING_REVIEW:
            logger.warning("Change request %s is not pending review", request_id)
            return None
        now = datetime.now(timezone.utc).isoformat()
        req.status = ChangeStatus.REJECTED
        req.reviewer = user
        req.reviewed_at = now
        req.metadata["rejection_reason"] = reason

        for change in req.changes:
            if change.id in self._changes:
                self._changes[change.id].status = ChangeStatus.REJECTED

        self._add_notification(
            request_id,
            req.requester,
            f"Change request '{req.title}' rejected by {user}: {reason}",
        )
        self._save()
        logger.info("Change request %s rejected by %s", request_id, user)
        return req

    def execute_change_request(self, request_id: str) -> Optional[ChangeRequest]:
        self._telemetry["execute_change_request_calls"] += 1
        req = self._requests.get(request_id)
        if not req:
            logger.warning("Change request not found: %s", request_id)
            return None
        if req.status != ChangeStatus.APPROVED:
            logger.warning("Change request %s must be approved before execution (status: %s)", request_id, req.status.value)
            return None

        now = datetime.now(timezone.utc).isoformat()
        req.status = ChangeStatus.IN_PROGRESS

        all_succeeded = True
        for change in req.changes:
            record = self._changes.get(change.id)
            if not record:
                continue
            try:
                record.status = ChangeStatus.IN_PROGRESS
                record.performed_at = now
                record.status = ChangeStatus.COMPLETED
                record.completed_at = datetime.now(timezone.utc).isoformat()
            except Exception:
                record.status = ChangeStatus.FAILED
                all_succeeded = False

        req.status = ChangeStatus.COMPLETED if all_succeeded else ChangeStatus.FAILED
        req.completed_at = datetime.now(timezone.utc).isoformat()

        self._add_notification(
            request_id,
            req.requester,
            f"Change request '{req.title}' {'completed successfully' if all_succeeded else 'failed during execution'}",
        )
        self._save()
        logger.info("Executed change request %s: %s", request_id, "success" if all_succeeded else "failed")
        return req

    def create_change_window(self, window: ChangeWindow) -> ChangeWindow:
        self._telemetry["create_change_window_calls"] += 1
        if window.id in self._windows:
            raise ValueError(f"Change window with id '{window.id}' already exists.")
        window.created_at = datetime.now(timezone.utc).isoformat()
        self._windows[window.id] = window
        self._save()
        logger.info("Created change window: %s (%s)", window.name, window.id)
        return window

    def is_in_change_window(self, change_type: ChangeType, severity: ChangeSeverity) -> bool:
        self._telemetry["is_in_change_window_calls"] += 1
        now = datetime.now(timezone.utc)
        for window in self._windows.values():
            if not window.is_active:
                continue
            try:
                start = datetime.fromisoformat(window.start_time)
                end = datetime.fromisoformat(window.end_time)
            except (ValueError, TypeError):
                continue
            if start <= now <= end:
                if _severity_rank.get(severity, 0) > _severity_rank.get(window.max_severity, 0):
                    continue
                if change_type not in window.allowed_change_types:
                    continue
                return True
        return False

    def get_change_history(self, entity: ChangeEntity, entity_id: str) -> list[ChangeRecord]:
        self._telemetry["get_change_history_calls"] += 1
        results = []
        for change in self._changes.values():
            if change.entity == entity and change.entity_id == entity_id:
                results.append(change)
        return sorted(results, key=lambda c: c.created_at, reverse=True)

    def get_change_stats(self, org_id: str) -> dict:
        self._telemetry["get_change_stats_calls"] += 1
        changes = [c for c in self._changes.values() if c.org_id == org_id]
        type_counts = defaultdict(int)
        severity_counts = defaultdict(int)
        status_counts = defaultdict(int)
        entity_counts = defaultdict(int)
        source_counts = defaultdict(int)
        for c in changes:
            type_counts[c.change_type.value] += 1
            severity_counts[c.severity.value] += 1
            status_counts[c.status.value] += 1
            entity_counts[c.entity.value] += 1
            source_counts[c.source.value] += 1
        return {
            "org_id": org_id,
            "total_changes": len(changes),
            "total_requests": sum(1 for r in self._requests.values() if r.org_id == org_id),
            "total_windows": sum(1 for w in self._windows.values() if w.org_id == org_id),
            "type_distribution": dict(type_counts),
            "severity_distribution": dict(severity_counts),
            "status_distribution": dict(status_counts),
            "entity_distribution": dict(entity_counts),
            "source_distribution": dict(source_counts),
        }

    def get_recent_changes(self, org_id: str, limit: int = 20) -> list[ChangeRecord]:
        self._telemetry["get_recent_changes_calls"] += 1
        org_changes = [c for c in self._changes.values() if c.org_id == org_id]
        sorted_changes = sorted(org_changes, key=lambda c: c.created_at, reverse=True)
        return sorted_changes[:limit]

    def get_telemetry(self) -> dict:
        return dict(self._telemetry)
