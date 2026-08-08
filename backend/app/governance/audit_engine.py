import json
import uuid
import os
import logging
import shutil
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


class AuditEventType(Enum):
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    REPOSITORY_ACCESS = "repository_access"
    POLICY_DECISION = "policy_decision"
    DEPLOYMENT = "deployment"
    AI_REQUEST = "ai_request"
    PROMPT_CHANGE = "prompt_change"
    MODEL_CHANGE = "model_change"
    SECURITY_EVENT = "security_event"
    ADMIN_ACTION = "admin_action"
    BILLING_EVENT = "billing_event"
    WORKSPACE_CHANGE = "workspace_change"
    USER_MANAGEMENT = "user_management"
    INTEGRATION_CHANGE = "integration_change"
    DATA_EXPORT = "data_export"
    DATA_DELETION = "data_deletion"


class AuditSeverity(Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AuditStatus(Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"
    PENDING = "pending"
    REVIEW_REQUIRED = "review_required"


class AuditRetention(Enum):
    DAYS_30 = "30d"
    DAYS_90 = "90d"
    DAYS_365 = "365d"
    YEARS_3 = "3y"
    YEARS_7 = "7y"
    FOREVER = "forever"


@dataclass
class AuditEvent:
    id: str
    org_id: str
    workspace_id: str = ""
    event_type: AuditEventType = AuditEventType.AUTHENTICATION
    severity: AuditSeverity = AuditSeverity.INFO
    status: AuditStatus = AuditStatus.SUCCESS
    action: str = ""
    resource_type: str = ""
    resource_id: str = ""
    actor_id: str = ""
    actor_type: str = ""
    source_ip: str = ""
    user_agent: str = ""
    session_id: str = ""
    request_id: str = ""
    changes: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    recorded_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["event_type"] = self.event_type.value
        d["severity"] = self.severity.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AuditEvent":
        data["event_type"] = AuditEventType(data["event_type"])
        data["severity"] = AuditSeverity(data["severity"])
        data["status"] = AuditStatus(data["status"])
        return cls(**data)


@dataclass
class AuditTrail:
    id: str
    org_id: str
    entity_type: str
    entity_id: str
    events: list[str] = field(default_factory=list)
    start_date: str = ""
    end_date: str = ""
    event_count: int = 0
    summary: dict = field(default_factory=dict)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AuditTrail":
        return cls(**data)


@dataclass
class AuditPolicy:
    id: str
    org_id: str
    name: str
    event_types: list[AuditEventType] = field(default_factory=list)
    retention: AuditRetention = AuditRetention.DAYS_90
    alert_on: list[AuditEventType] = field(default_factory=list)
    notify_roles: list = field(default_factory=list)
    enabled: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["event_types"] = [t.value for t in self.event_types]
        d["retention"] = self.retention.value
        d["alert_on"] = [t.value for t in self.alert_on]
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AuditPolicy":
        data["event_types"] = [AuditEventType(t) for t in data["event_types"]]
        data["retention"] = AuditRetention(data["retention"])
        data["alert_on"] = [AuditEventType(t) for t in data["alert_on"]]
        return cls(**data)


@dataclass
class AuditExport:
    id: str
    org_id: str
    date_range_start: str
    date_range_end: str
    event_types: list[AuditEventType] = field(default_factory=list)
    format: str = "json"
    status: str = "pending"
    file_path: str = ""
    record_count: int = 0
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_at: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["event_types"] = [t.value for t in self.event_types]
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AuditExport":
        data["event_types"] = [AuditEventType(t) for t in data["event_types"]]
        return cls(**data)


_RETENTION_DELTAS = {
    AuditRetention.DAYS_30: timedelta(days=30),
    AuditRetention.DAYS_90: timedelta(days=90),
    AuditRetention.DAYS_365: timedelta(days=365),
    AuditRetention.YEARS_3: timedelta(days=3 * 365),
    AuditRetention.YEARS_7: timedelta(days=7 * 365),
}


class AuditEngine:
    def __init__(self, storage_dir: str = "audit_engine_data"):
        self.storage_dir = storage_dir
        self._events: dict[str, AuditEvent] = {}
        self._policies: dict[str, AuditPolicy] = {}
        self._exports: dict[str, AuditExport] = {}
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _events_path(self) -> str:
        return os.path.join(self.storage_dir, "events.json")

    def _policies_path(self) -> str:
        return os.path.join(self.storage_dir, "policies.json")

    def _exports_path(self) -> str:
        return os.path.join(self.storage_dir, "exports.json")

    def _save(self) -> None:
        try:
            events_data = {eid: e.to_dict() for eid, e in self._events.items()}
            with open(self._events_path(), "w", encoding="utf-8") as f:
                json.dump(events_data, f, indent=2, default=str)

            policies_data = {pid: p.to_dict() for pid, p in self._policies.items()}
            with open(self._policies_path(), "w", encoding="utf-8") as f:
                json.dump(policies_data, f, indent=2, default=str)

            exports_data = {xid: x.to_dict() for xid, x in self._exports.items()}
            with open(self._exports_path(), "w", encoding="utf-8") as f:
                json.dump(exports_data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save audit engine data: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._events_path()):
                with open(self._events_path(), "r", encoding="utf-8") as f:
                    events_data = json.load(f)
                for eid, data in events_data.items():
                    try:
                        self._events[eid] = AuditEvent.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed audit event %s: %s", eid, e)

            if os.path.exists(self._policies_path()):
                with open(self._policies_path(), "r", encoding="utf-8") as f:
                    policies_data = json.load(f)
                for pid, data in policies_data.items():
                    try:
                        self._policies[pid] = AuditPolicy.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed audit policy %s: %s", pid, e)

            if os.path.exists(self._exports_path()):
                with open(self._exports_path(), "r", encoding="utf-8") as f:
                    exports_data = json.load(f)
                for xid, data in exports_data.items():
                    try:
                        self._exports[xid] = AuditExport.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed audit export %s: %s", xid, e)
        except Exception as e:
            logger.error("Failed to load audit engine data: %s", e, exc_info=True)

    def record_event(self, event: AuditEvent) -> AuditEvent:
        self._telemetry["record_event_calls"] += 1
        if event.id in self._events:
            raise ValueError(f"Audit event with id '{event.id}' already exists.")
        now = datetime.now(timezone.utc).isoformat()
        event.recorded_at = now
        if not event.timestamp:
            event.timestamp = now
        self._events[event.id] = event
        self.apply_retention_policy()
        self._save()
        logger.debug("Recorded audit event: %s (%s)", event.id, event.event_type.value)
        return event

    def get_event(self, event_id: str) -> Optional[AuditEvent]:
        self._telemetry["get_event_calls"] += 1
        return self._events.get(event_id)

    def search_events(self, org_id: str, event_type: Optional[AuditEventType] = None,
                      severity: Optional[AuditSeverity] = None,
                      actor_id: Optional[str] = None,
                      resource_type: Optional[str] = None,
                      start_date: Optional[str] = None,
                      end_date: Optional[str] = None,
                      limit: int = 100) -> list[AuditEvent]:
        self._telemetry["search_events_calls"] += 1
        results = []
        for event in self._events.values():
            if event.org_id != org_id:
                continue
            if event_type and event.event_type != event_type:
                continue
            if severity and event.severity != severity:
                continue
            if actor_id and event.actor_id != actor_id:
                continue
            if resource_type and event.resource_type != resource_type:
                continue
            if start_date:
                try:
                    if event.timestamp < start_date:
                        continue
                except (ValueError, TypeError):
                    pass
            if end_date:
                try:
                    if event.timestamp > end_date:
                        continue
                except (ValueError, TypeError):
                    pass
            results.append(event)

        results.sort(key=lambda e: e.timestamp, reverse=True)
        return results[:limit]

    def get_entity_trail(self, entity_type: str, entity_id: str) -> AuditTrail:
        self._telemetry["get_entity_trail_calls"] += 1
        matched = []
        for event in self._events.values():
            if event.resource_type == entity_type and event.resource_id == entity_id:
                matched.append(event)
        matched.sort(key=lambda e: e.timestamp)

        event_ids = [e.id for e in matched]
        summary = defaultdict(int)
        for e in matched:
            summary[e.event_type.value] += 1
            summary[f"severity:{e.severity.value}"] += 1
            summary[f"status:{e.status.value}"] += 1

        trail = AuditTrail(
            id=str(uuid.uuid4()),
            org_id=matched[0].org_id if matched else "",
            entity_type=entity_type,
            entity_id=entity_id,
            events=event_ids,
            start_date=matched[0].timestamp if matched else "",
            end_date=matched[-1].timestamp if matched else "",
            event_count=len(matched),
            summary=dict(summary),
        )
        self._telemetry["entity_trails_generated"] += 1
        return trail

    def get_user_activity(self, user_id: str, days: int = 90) -> list[AuditEvent]:
        self._telemetry["get_user_activity_calls"] += 1
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        results = []
        for event in self._events.values():
            if event.actor_id != user_id:
                continue
            try:
                if event.timestamp < cutoff:
                    continue
            except (ValueError, TypeError):
                pass
            results.append(event)
        results.sort(key=lambda e: e.timestamp, reverse=True)
        return results

    def get_recent_events(self, org_id: str, limit: int = 50,
                          severity: Optional[AuditSeverity] = None) -> list[AuditEvent]:
        self._telemetry["get_recent_events_calls"] += 1
        results = []
        for event in self._events.values():
            if event.org_id != org_id:
                continue
            if severity and event.severity != severity:
                continue
            results.append(event)
        results.sort(key=lambda e: e.recorded_at, reverse=True)
        return results[:limit]

    def create_audit_policy(self, policy: AuditPolicy) -> AuditPolicy:
        self._telemetry["create_audit_policy_calls"] += 1
        if policy.id in self._policies:
            raise ValueError(f"Audit policy with id '{policy.id}' already exists.")
        policy.created_at = datetime.now(timezone.utc).isoformat()
        self._policies[policy.id] = policy
        self._save()
        logger.info("Created audit policy: %s (%s)", policy.name, policy.id)
        return policy

    def list_audit_policies(self, org_id: str) -> list[AuditPolicy]:
        self._telemetry["list_audit_policies_calls"] += 1
        return [p for p in self._policies.values() if p.org_id == org_id]

    def get_event_stats(self, org_id: str, days: int = 30) -> dict:
        self._telemetry["get_event_stats_calls"] += 1
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        filtered = []
        for event in self._events.values():
            if event.org_id != org_id:
                continue
            try:
                if event.timestamp < cutoff:
                    continue
            except (ValueError, TypeError):
                pass
            filtered.append(event)

        by_type = defaultdict(int)
        by_severity = defaultdict(int)
        by_status = defaultdict(int)
        by_actor = defaultdict(int)
        by_resource = defaultdict(int)

        for e in filtered:
            by_type[e.event_type.value] += 1
            by_severity[e.severity.value] += 1
            by_status[e.status.value] += 1
            by_actor[e.actor_id] += 1
            by_resource[e.resource_type] += 1

        severity_scores = {
            AuditSeverity.DEBUG: 0,
            AuditSeverity.INFO: 1,
            AuditSeverity.WARNING: 2,
            AuditSeverity.ERROR: 3,
            AuditSeverity.CRITICAL: 4,
        }
        total_score = sum(severity_scores.get(e.severity, 0) for e in filtered)
        avg_severity = round(total_score / len(filtered), 2) if filtered else 0.0

        return {
            "org_id": org_id,
            "period_days": days,
            "total_events": len(filtered),
            "by_type": dict(by_type),
            "by_severity": dict(by_severity),
            "by_status": dict(by_status),
            "top_actors": dict(sorted(by_actor.items(), key=lambda x: x[1], reverse=True)[:10]),
            "top_resources": dict(sorted(by_resource.items(), key=lambda x: x[1], reverse=True)[:10]),
            "average_severity_score": avg_severity,
            "telemetry": dict(self._telemetry),
        }

    def export_audit_log(self, org_id: str, start_date: str, end_date: str,
                         event_types: list[AuditEventType], format: str = "json") -> AuditExport:
        self._telemetry["export_audit_log_calls"] += 1
        matched = []
        for event in self._events.values():
            if event.org_id != org_id:
                continue
            if event_types and event.event_type not in event_types:
                continue
            try:
                if event.timestamp < start_date:
                    continue
                if event.timestamp > end_date:
                    continue
            except (ValueError, TypeError):
                pass
            matched.append(event)

        matched.sort(key=lambda e: e.timestamp)

        export_id = str(uuid.uuid4())
        file_name = f"audit_export_{org_id}_{export_id[:8]}.{format}"
        file_path = os.path.join(self.storage_dir, file_name)

        try:
            export_data = [e.to_dict() for e in matched]
            if format == "json":
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(export_data, f, indent=2, default=str)
            else:
                lines = []
                if format == "csv":
                    if export_data:
                        headers = list(export_data[0].keys())
                        lines.append(",".join(headers))
                        for row in export_data:
                            lines.append(",".join(str(row.get(h, "")) for h in headers))
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write("\n".join(lines))

            expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        except Exception as e:
            logger.error("Failed to write audit export: %s", e, exc_info=True)
            file_path = ""
            expires_at = ""

        export_record = AuditExport(
            id=export_id,
            org_id=org_id,
            date_range_start=start_date,
            date_range_end=end_date,
            event_types=event_types,
            format=format,
            status="completed" if file_path else "failed",
            file_path=file_path,
            record_count=len(matched),
            expires_at=expires_at,
        )
        self._exports[export_record.id] = export_record
        self._save()
        logger.info("Exported audit log: %s (%d records)", export_id, len(matched))
        return export_record

    def apply_retention_policy(self) -> int:
        self._telemetry["apply_retention_policy_calls"] += 1
        now = datetime.now(timezone.utc)
        removed = 0

        org_retention: dict[str, AuditRetention] = {}
        for policy in self._policies.values():
            if policy.enabled and policy.org_id not in org_retention:
                org_retention[policy.org_id] = policy.retention

        event_ids_to_remove = []
        for eid, event in self._events.items():
            cutoff = None
            if event.org_id in org_retention:
                retention = org_retention[event.org_id]
            else:
                retention = AuditRetention.DAYS_365

            if retention == AuditRetention.FOREVER:
                continue
            delta = _RETENTION_DELTAS.get(retention)
            if not delta:
                continue
            try:
                event_time = datetime.fromisoformat(event.timestamp)
            except (ValueError, TypeError):
                event_time = datetime.fromisoformat(event.recorded_at)
            if now - event_time > delta:
                event_ids_to_remove.append(eid)

        for eid in event_ids_to_remove:
            del self._events[eid]
            removed += 1

        if removed > 0:
            self._save()
            logger.info("Applied retention policy: removed %d events", removed)

        self._telemetry["events_removed_by_retention"] += removed
        return removed

    def get_telemetry(self) -> dict:
        return dict(self._telemetry)
