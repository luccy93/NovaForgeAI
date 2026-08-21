"""Unified Analytics Platform -- Security Analytics (Volume 50).

In-memory security analytics integrating Volume 47 scanner data:
findings, scans, gate failures, trends, and remediation velocity.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone


SEVERITY_ORDER = ("critical", "high", "medium", "low", "info")


def _utcnow() -> datetime:
    return datetime.utcnow()


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def _parse_ts(value) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _in_window(dt: datetime | None, start: datetime | None, end: datetime | None) -> bool:
    if dt is None:
        return True
    if start is not None and dt < start:
        return False
    if end is not None and dt > end:
        return False
    return True


def _mean(values) -> float:
    return sum(values) / len(values) if values else 0.0


def _median(values) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return (float(ordered[mid - 1]) + float(ordered[mid])) / 2.0


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _bucket_label(dt: datetime, granularity: str) -> str:
    g = str(granularity).lower()
    if g == "minute":
        return dt.strftime("%Y-%m-%dT%H:%M")
    if g == "hour":
        return dt.strftime("%Y-%m-%dT%H")
    if g == "week":
        anchor = (dt - timedelta(days=dt.weekday())).date()
        return anchor.isoformat()
    if g == "month":
        return dt.strftime("%Y-%m")
    return dt.strftime("%Y-%m-%d")


class SecurityAnalyticsService:
    """In-memory security analytics store."""

    def __init__(self) -> None:
        self._findings: list[dict] = []
        self._scans: list[dict] = []
        self._gate_failures: list[dict] = []

    # ── Recording ─────────────────────────────────────────────────────

    def record_security_finding(self, tenant: str, repository: str = "",
                                severity: str = "medium", category: str = "",
                                title: str = "", file_path: str = "",
                                remediated: bool = False,
                                detected_at: str = "") -> dict:
        detected_dt = _parse_ts(detected_at) or _utcnow()
        severity_key = str(severity).lower()
        fingerprint = hashlib.sha256(
            "|".join([tenant, repository, category, title, file_path]).encode("utf-8")
        ).hexdigest()[:16]
        record = {
            "id": uuid.uuid4().hex,
            "tenant": tenant,
            "repository": repository,
            "severity": severity_key,
            "category": category,
            "title": title,
            "file_path": file_path,
            "fingerprint": fingerprint,
            "remediated": bool(remediated),
            "detected_at": _iso(detected_dt),
            "_dt": detected_dt,
            "remediated_at": _iso(_utcnow()) if remediated else "",
        }
        if remediated:
            record["remediation_minutes"] = round(
                max(0.0, (_parse_ts(record["remediated_at"]) - detected_dt).total_seconds() / 60.0), 4
            )
        else:
            record["remediation_minutes"] = None
        self._findings.append(record)
        return {k: v for k, v in record.items() if k != "_dt"}

    def record_security_scan(self, tenant: str, repository: str = "",
                             findings_count: int = 0, critical: int = 0,
                             high: int = 0, medium: int = 0, low: int = 0,
                             scan_duration_ms: float = 0) -> dict:
        ts = _utcnow()
        counts = {
            "critical": int(critical or 0),
            "high": int(high or 0),
            "medium": int(medium or 0),
            "low": int(low or 0),
        }
        record = {
            "id": uuid.uuid4().hex,
            "tenant": tenant,
            "repository": repository,
            "findings_count": int(findings_count or 0),
            "critical": counts["critical"],
            "high": counts["high"],
            "medium": counts["medium"],
            "low": counts["low"],
            "severity_counts_json": json.dumps(counts, sort_keys=True),
            "scan_duration_ms": float(scan_duration_ms or 0),
            "scanned_at": _iso(ts),
            "_dt": ts,
        }
        self._scans.append(record)
        return {k: v for k, v in record.items() if k != "_dt"}

    def record_gate_failure(self, tenant: str, repository: str = "",
                            reason: str = "") -> dict:
        ts = _utcnow()
        record = {
            "id": uuid.uuid4().hex,
            "tenant": tenant,
            "repository": repository,
            "reason": reason,
            "failed_at": _iso(ts),
            "_dt": ts,
        }
        self._gate_failures.append(record)
        return {k: v for k, v in record.items() if k != "_dt"}

    # ── Filtering helpers ─────────────────────────────────────────────

    def _window_findings(self, tenant: str, repository: str = "",
                         start_time: str = "", end_time: str = "") -> list[dict]:
        start_dt, end_dt = _parse_ts(start_time), _parse_ts(end_time)
        return [
            f for f in self._findings
            if f["tenant"] == tenant
            and _in_window(f["_dt"], start_dt, end_dt)
            and (not repository or f["repository"] == repository)
        ]

    def _window_scans(self, tenant: str, repository: str = "",
                      start_time: str = "", end_time: str = "") -> list[dict]:
        start_dt, end_dt = _parse_ts(start_time), _parse_ts(end_time)
        return [
            s for s in self._scans
            if s["tenant"] == tenant
            and _in_window(s["_dt"], start_dt, end_dt)
            and (not repository or s["repository"] == repository)
        ]

    def _window_gate_failures(self, tenant: str, start_time: str = "",
                              end_time: str = "") -> list[dict]:
        start_dt, end_dt = _parse_ts(start_time), _parse_ts(end_time)
        return [
            g for g in self._gate_failures
            if g["tenant"] == tenant and _in_window(g["_dt"], start_dt, end_dt)
        ]

    # ── Summary ───────────────────────────────────────────────────────

    def get_security_summary(self, tenant: str, repository: str = "",
                             start_time: str = "", end_time: str = "") -> dict:
        findings = self._window_findings(tenant, repository, start_time, end_time)
        scans = self._window_scans(tenant, repository, start_time, end_time)
        gates = self._window_gate_failures(tenant, start_time, end_time)
        by_severity = {level: 0 for level in SEVERITY_ORDER}
        for finding in findings:
            by_severity[finding["severity"]] = by_severity.get(finding["severity"], 0) + 1
        remediated = sum(1 for f in findings if f["remediated"])
        open_findings = len(findings) - remediated
        open_critical = sum(1 for f in findings if not f["remediated"] and f["severity"] == "critical")
        return {
            "total_findings": len(findings),
            "by_severity": by_severity,
            "remediated_findings": remediated,
            "open_findings": open_findings,
            "open_critical": open_critical,
            "remediation_rate": _rate(remediated, len(findings)),
            "repositories": len({f["repository"] for f in findings} - {""}),
            "scans_count": len(scans),
            "scan_findings_total": sum(s["findings_count"] for s in scans),
            "scan_critical_total": sum(s["critical"] for s in scans),
            "avg_scan_duration_ms": round(_mean([s["scan_duration_ms"] for s in scans]), 4),
            "gate_failures": len(gates),
        }

    # ── Trends ────────────────────────────────────────────────────────

    def get_finding_trends(self, tenant: str, granularity: str = "day",
                           start_time: str = "", end_time: str = "") -> list[dict]:
        findings = self._window_findings(tenant, start_time=start_time, end_time=end_time)
        buckets: dict[str, dict] = {}
        for finding in findings:
            label = _bucket_label(finding["_dt"], granularity)
            bucket = buckets.setdefault(label, {
                "period": label,
                "findings": 0,
                "remediated": 0,
                "critical": 0,
                "high": 0,
            })
            bucket["findings"] += 1
            bucket["remediated"] += 1 if finding["remediated"] else 0
            if finding["severity"] == "critical":
                bucket["critical"] += 1
            elif finding["severity"] == "high":
                bucket["high"] += 1
        return [buckets[key] for key in sorted(buckets)]

    # ── Risk ──────────────────────────────────────────────────────────

    def get_repositories_at_risk(self, tenant: str, threshold: int = 5) -> list[dict]:
        grouped: dict[str, list[dict]] = {}
        for finding in self._findings:
            if finding["tenant"] != tenant:
                continue
            grouped.setdefault(finding["repository"], []).append(finding)

        at_risk: list[dict] = []
        for repository, rows in grouped.items():
            critical = sum(1 for f in rows if f["severity"] == "critical")
            high = sum(1 for f in rows if f["severity"] == "high")
            if critical < threshold:
                continue
            at_risk.append({
                "repository": repository,
                "total_findings": len(rows),
                "critical_count": critical,
                "high_count": high,
                "open_critical": sum(1 for f in rows if f["severity"] == "critical" and not f["remediated"]),
                "remediation_rate": _rate(sum(1 for f in rows if f["remediated"]), len(rows)),
            })
        at_risk.sort(key=lambda item: (item["critical_count"], item["high_count"]), reverse=True)
        return at_risk

    # ── Remediation velocity ──────────────────────────────────────────

    def get_remediation_time(self, tenant: str, start_time: str = "",
                             end_time: str = "") -> dict:
        findings = self._window_findings(tenant, start_time=start_time, end_time=end_time)
        durations = [
            f for f in findings
            if f["remediated"] and f["remediation_minutes"] is not None
        ]
        by_severity: dict[str, dict] = {}
        for level in SEVERITY_ORDER:
            values = [f["remediation_minutes"] for f in durations if f["severity"] == level]
            if not values:
                continue
            by_severity[level] = {
                "avg_minutes": round(_mean(values), 4),
                "median_minutes": round(_median(values), 4),
                "count": len(values),
            }
        overall = [f["remediation_minutes"] for f in durations]
        return {
            "by_severity": by_severity,
            "overall_avg_minutes": round(_mean(overall), 4),
            "overall_median_minutes": round(_median(overall), 4),
            "remediated_count": len(durations),
        }


security_analytics_service = SecurityAnalyticsService()
