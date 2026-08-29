"""Event normalization — Volume 63.

Converts raw telemetry from IAM/audit/observability/CI/CD/deployment/AI/agent/
marketplace/datagov/network/cloud into common schema. Preserves original metadata.
Do not duplicate telemetry storage — normalized event keeps pointer to original.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from app.secops.models import EVENT_CATEGORIES, SEVERITIES

# Valid sources (integrated existing)
VALID_SOURCES = {
    "IAM", "audit", "application_logs", "observability", "CICD", "deployment",
    "AI_runtime", "agent_runtime", "marketplace", "data_governance",
    "network", "cloud", "unknown",
}

SEVERITY_DEFAULT = "INFO"
CATEGORY_DEFAULT = "APPLICATION"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_event(raw: dict, source: str | None = None) -> dict:
    """Convert raw event dict to normalized security event.

    Required normalized fields: event_id, tenant, source, resource, actor, action,
    severity, category, timestamp, region, request_id, trace_id.
    Preserves original in source_metadata + original_event_id.
    """
    src = source or raw.get("source") or "unknown"
    if src not in VALID_SOURCES:
        src = "unknown"

    # Resolve tenant — never infer, use explicit
    tenant = raw.get("tenant") or raw.get("organization_id") or raw.get("org_id") or "default"
    tenant = str(tenant)

    # Severity evidence-driven, fallback INFO
    sev = (raw.get("severity") or raw.get("level") or SEVERITY_DEFAULT).upper()
    if sev not in SEVERITIES:
        sev = SEVERITY_DEFAULT

    cat = (raw.get("category") or raw.get("event_category") or CATEGORY_DEFAULT).upper()
    if cat not in EVENT_CATEGORIES:
        cat = CATEGORY_DEFAULT

    ts = raw.get("timestamp") or raw.get("created_at") or raw.get("event_time") or _now_iso()
    # ensure iso
    if isinstance(ts, datetime):
        ts = ts.isoformat()

    event_id = raw.get("event_id") or raw.get("id") or str(uuid.uuid4())
    normalized = {
        "event_id": str(event_id),
        "tenant": tenant,
        "source": src,
        "resource": str(raw.get("resource") or raw.get("resource_id") or raw.get("target") or ""),
        "resource_type": str(raw.get("resource_type") or ""),
        "actor": str(raw.get("actor") or raw.get("actor_id") or raw.get("user_id") or raw.get("service_account") or ""),
        "action": str(raw.get("action") or raw.get("event_type") or raw.get("type") or ""),
        "severity": sev,
        "category": cat,
        "timestamp": ts,
        "region": str(raw.get("region") or raw.get("region_id") or ""),
        "request_id": str(raw.get("request_id") or raw.get("requestId") or ""),
        "trace_id": str(raw.get("trace_id") or raw.get("traceId") or ""),
        "ip": str(raw.get("ip") or raw.get("ip_address") or raw.get("client_ip") or ""),
        "deployment_id": str(raw.get("deployment_id") or raw.get("deployment") or ""),
        "original_event_id": str(raw.get("id") or raw.get("event_id") or ""),
        "source_metadata": {k: v for k, v in raw.items() if k not in {"event_id", "tenant", "source", "resource", "actor", "action", "severity", "category", "timestamp", "region", "request_id", "trace_id"}},
    }
    return normalized


def validate_normalized(event: dict) -> list[str]:
    """Return list of validation errors; empty if valid."""
    errors = []
    required = ["event_id", "tenant", "source", "severity", "category", "timestamp"]
    for f in required:
        if not event.get(f):
            errors.append(f"missing {f}")
    if event.get("severity") and event["severity"] not in SEVERITIES:
        errors.append(f"invalid severity {event['severity']}")
    if event.get("category") and event["category"] not in EVENT_CATEGORIES:
        errors.append(f"invalid category {event['category']}")
    return errors


# In-memory bounded retention for recent normalized events (reuse pattern, not duplicate store)
_recent_events: list[dict] = []
_MAX_RECENT = 10000


def retain_event(event: dict) -> None:
    _recent_events.append(event)
    if len(_recent_events) > _MAX_RECENT:
        del _recent_events[0: len(_recent_events) - _MAX_RECENT]


def get_recent_events(tenant: str | None = None, limit: int = 100) -> list[dict]:
    if tenant:
        filtered = [e for e in _recent_events if e.get("tenant") == tenant]
        return filtered[-limit:]
    return _recent_events[-limit:]


def clear_recent() -> None:
    _recent_events.clear()
