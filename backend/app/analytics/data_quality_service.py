"""NovaForge Analytics Platform -- Data Quality Service (Volume 50).

In-memory data quality validation for analytics events: missing fields,
invalid timestamps, negative costs, impossible durations, duplicate
event identifiers and ingestion gaps.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

REQUIRED_EVENT_FIELDS = ("event_id", "event_type", "timestamp")
MAX_DURATION_MS = 30 * 24 * 60 * 60 * 1000
MISSING_EVENTS_RATIO_THRESHOLD = 0.01
MISSING_EVENTS_ABSOLUTE_THRESHOLD = 10
MAX_STORED_ISSUES = 5000

SEVERITY_LOW = "low"
SEVERITY_MEDIUM = "medium"
SEVERITY_HIGH = "high"
SEVERITY_CRITICAL = "critical"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_ts(value: str) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


class DataQualityService:
    """Validates analytics events and tracks data quality issues."""

    def __init__(self):
        self._issues: list[dict] = []

    # ── Event validation ───────────────────────────────────────────────

    def validate_event(self, event: dict, tenant: str = "default") -> list[dict]:
        if not isinstance(event, dict):
            return [self._make_issue(tenant, "invalid_event", "",
                                     "Event payload must be a JSON object.",
                                     SEVERITY_HIGH)]
        issues: list[dict] = []
        for field in REQUIRED_EVENT_FIELDS:
            value = event.get(field)
            if value is None or (isinstance(value, str) and not value.strip()):
                issues.append(self._make_issue(
                    tenant, "missing_field", field,
                    f"Required field '{field}' is missing or empty.",
                    SEVERITY_HIGH))
        timestamp = event.get("timestamp")
        if timestamp is not None and (not isinstance(timestamp, str)
                                      or not timestamp.strip()
                                      or _parse_ts(timestamp) is None):
            issues.append(self._make_issue(
                tenant, "invalid_timestamp", "timestamp",
                "Field 'timestamp' must be a valid ISO-8601 string.",
                SEVERITY_HIGH))
        cost = event.get("cost_usd")
        if cost is not None:
            try:
                cost_value = float(cost)
            except (TypeError, ValueError):
                cost_value = None
            if cost_value is None:
                issues.append(self._make_issue(
                    tenant, "invalid_cost", "cost_usd",
                    "Field 'cost_usd' must be numeric.", SEVERITY_MEDIUM))
            elif cost_value < 0:
                issues.append(self._make_issue(
                    tenant, "negative_cost", "cost_usd",
                    f"Field 'cost_usd' is negative ({cost_value}).",
                    SEVERITY_HIGH))
        duration = event.get("duration_ms")
        if duration is not None:
            try:
                duration_value = float(duration)
            except (TypeError, ValueError):
                duration_value = None
            if duration_value is None:
                issues.append(self._make_issue(
                    tenant, "impossible_duration", "duration_ms",
                    "Field 'duration_ms' must be numeric.", SEVERITY_MEDIUM))
            elif duration_value < 0:
                issues.append(self._make_issue(
                    tenant, "impossible_duration", "duration_ms",
                    f"Field 'duration_ms' is negative ({duration_value}).",
                    SEVERITY_HIGH))
            elif duration_value > MAX_DURATION_MS:
                issues.append(self._make_issue(
                    tenant, "impossible_duration", "duration_ms",
                    f"Field 'duration_ms' exceeds the maximum plausible "
                    f"duration ({duration_value} ms).",
                    SEVERITY_MEDIUM))
        return issues

    # ── Duplicates ─────────────────────────────────────────────────────

    def detect_duplicates(self, events: list[dict]) -> list[dict]:
        by_id: dict[str, list[int]] = {}
        by_content: dict[str, list[int]] = {}
        for index, event in enumerate(events or []):
            event_id = ""
            if isinstance(event, dict):
                event_id = str(event.get("event_id") or "")
            if event_id:
                by_id.setdefault(event_id, []).append(index)
            else:
                fingerprint = hashlib.sha256(
                    json.dumps(event, sort_keys=True, default=str).encode("utf-8")
                ).hexdigest()
                by_content.setdefault(fingerprint, []).append(index)
        duplicates: list[dict] = []
        for event_id, indices in by_id.items():
            if len(indices) > 1:
                duplicates.append({"event_id": event_id,
                                   "match_type": "event_id",
                                   "occurrences": len(indices),
                                   "indices": indices})
        for fingerprint, indices in by_content.items():
            if len(indices) > 1:
                duplicates.append({"event_id": "",
                                   "fingerprint": fingerprint,
                                   "match_type": "content_hash",
                                   "occurrences": len(indices),
                                   "indices": indices})
        return duplicates

    # ── Ingestion gaps ─────────────────────────────────────────────────

    def check_missing_events(self, tenant: str, expected_count: int,
                             actual_count: int, source: str = "") -> dict | None:
        expected = int(expected_count)
        actual = int(actual_count)
        if expected <= 0:
            return None
        missing = expected - actual
        if missing <= 0:
            return None
        ratio = missing / expected
        if (ratio < MISSING_EVENTS_RATIO_THRESHOLD
                and missing < MISSING_EVENTS_ABSOLUTE_THRESHOLD):
            return None
        if ratio >= 0.10:
            severity = SEVERITY_CRITICAL
        elif ratio >= 0.02:
            severity = SEVERITY_HIGH
        else:
            severity = SEVERITY_MEDIUM
        description = (f"Ingestion gap for '{source or 'unknown'}': expected "
                       f"{expected} events, received {actual} "
                       f"({missing} missing, {ratio:.1%}).")
        return self.record_issue(
            tenant=tenant,
            issue_type="missing_events",
            source=source,
            description=description,
            severity=severity,
            resource_type="event_stream",
            resource_id=source,
            metadata={"expected_count": expected,
                      "actual_count": actual,
                      "missing_count": missing,
                      "missing_ratio": round(ratio, 4)})

    # ── Issue tracking ─────────────────────────────────────────────────

    def record_issue(self, tenant: str, issue_type: str, source: str,
                     description: str, severity: str = SEVERITY_LOW,
                     resource_type: str = "", resource_id: str = "",
                     metadata: dict | None = None) -> dict:
        issue = {
            "issue_id": uuid4().hex,
            "tenant": tenant,
            "issue_type": issue_type,
            "source": source,
            "description": description,
            "severity": severity,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "metadata": dict(metadata or {}),
            "resolved": False,
            "created_at": _utc_now(),
            "resolved_at": None,
        }
        self._issues.append(issue)
        if len(self._issues) > MAX_STORED_ISSUES:
            del self._issues[:len(self._issues) - MAX_STORED_ISSUES]
        return issue

    def get_issues(self, tenant: str = "", issue_type: str = "",
                   resolved: bool | None = None, limit: int = 100) -> list[dict]:
        selected = [
            issue for issue in reversed(self._issues)
            if (not tenant or issue["tenant"] == tenant)
            and (not issue_type or issue["issue_type"] == issue_type)
            and (resolved is None or issue["resolved"] == resolved)
        ]
        return selected[:max(0, limit)]

    def resolve_issue(self, issue_id: str) -> bool:
        for issue in self._issues:
            if issue["issue_id"] == issue_id:
                if not issue["resolved"]:
                    issue["resolved"] = True
                    issue["resolved_at"] = _utc_now()
                return True
        return False

    # ── Summary ────────────────────────────────────────────────────────

    def get_quality_summary(self, tenant: str = "") -> dict:
        selected = [issue for issue in self._issues
                    if not tenant or issue["tenant"] == tenant]
        by_type: dict[str, int] = {}
        by_severity: dict[str, int] = {}
        unresolved = 0
        for issue in selected:
            by_type[issue["issue_type"]] = by_type.get(issue["issue_type"], 0) + 1
            by_severity[issue["severity"]] = by_severity.get(issue["severity"], 0) + 1
            if not issue["resolved"]:
                unresolved += 1
        return {
            "total_issues": len(selected),
            "by_type": by_type,
            "by_severity": by_severity,
            "unresolved_count": unresolved,
            "resolved_count": len(selected) - unresolved,
        }

    # ── Batch validation ───────────────────────────────────────────────

    def validate_batch(self, events: list[dict], tenant: str = "default") -> dict:
        events = events or []
        issues: list[dict] = []
        invalid_indices: set[int] = set()
        for index, event in enumerate(events):
            event_issues = self.validate_event(event, tenant=tenant)
            if not event_issues:
                continue
            invalid_indices.add(index)
            for issue in event_issues:
                flagged = dict(issue)
                flagged["event_index"] = index
                issues.append(flagged)
        for duplicate in self.detect_duplicates(events):
            invalid_indices.update(duplicate["indices"])
            issues.append({
                "issue_type": "duplicate_event",
                "field": "event_id" if duplicate["match_type"] == "event_id" else "",
                "description": (f"Event appears {duplicate['occurrences']} times "
                                f"in batch ({duplicate['match_type']} match)."),
                "severity": SEVERITY_MEDIUM,
                "tenant": tenant,
                "detected_at": _utc_now(),
                "event_index": duplicate["indices"][0],
                "duplicate_indices": duplicate["indices"],
            })
        return {
            "total": len(events),
            "valid": len(events) - len(invalid_indices),
            "invalid": len(invalid_indices),
            "issues": issues,
        }

    # ── Helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _make_issue(tenant: str, issue_type: str, field: str,
                    description: str, severity: str) -> dict:
        return {"issue_type": issue_type,
                "field": field,
                "description": description,
                "severity": severity,
                "tenant": tenant,
                "detected_at": _utc_now()}


data_quality_service = DataQualityService()
