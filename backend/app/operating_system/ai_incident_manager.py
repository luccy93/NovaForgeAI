"""AI Incident Manager — failure detection, severity classification, log collection, root cause analysis, incident reports, MTTR tracking."""

import hashlib
import json
import re
import uuid
from collections import defaultdict
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional


class IncidentSeverity(Enum):
    CRITICAL = "critical"  # System down, data loss
    HIGH = "high"  # Major feature unavailable
    MEDIUM = "medium"  # Partial degradation
    LOW = "low"  # Minor issue, cosmetic


class IncidentStatus(Enum):
    DETECTED = "detected"
    ANALYZING = "analyzing"
    MITIGATING = "mitigating"
    RESOLVED = "resolved"
    CLOSED = "closed"


@dataclass
class Incident:
    id: str
    title: str
    severity: IncidentSeverity
    status: IncidentStatus = IncidentStatus.DETECTED
    source: str = ""  # build, deploy, runtime, security, performance
    description: str = ""
    affected_components: list[str] = field(default_factory=list)
    logs: list[dict] = field(default_factory=list)
    root_cause: str = ""
    timeline: list[dict] = field(default_factory=list)
    recommended_fix: str = ""
    fix_applied: bool = False
    detected_at: str = ""
    acknowledged_at: Optional[str] = None
    resolved_at: Optional[str] = None
    mttr_minutes: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class IncidentReport:
    repo_id: str
    repo_name: str
    timestamp: str
    active_incidents: list[Incident] = field(default_factory=list)
    resolved_incidents: list[Incident] = field(default_factory=list)
    total_incidents: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    avg_mttr_minutes: float = 0.0
    top_causes: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


class AIIncidentManager:
    """Autonomous incident management — detection, classification, RCA, reporting, MTTR tracking."""

    FAILURE_PATTERNS = {
        "import_error": (r"ImportError|ModuleNotFoundError", "Dependency missing or incorrect import path"),
        "syntax_error": (r"SyntaxError|IndentationError", "Code syntax error"),
        "connection_error": (r"ConnectionError|ConnectionRefused|ConnectionReset", "Network/service unavailable"),
        "timeout": (r"TimeoutError|asyncio\.TimeoutError|socket\.timeout", "Operation timed out"),
        "memory": (r"MemoryError|OutOfMemory|OOM", "Memory exhaustion"),
        "permission": (r"PermissionError|Permission denied|AccessDenied", "Insufficient permissions"),
        "value_error": (r"ValueError|TypeError|KeyError", "Invalid data or type mismatch"),
        "database": (r"DatabaseError|OperationalError|IntegrityError", "Database operation failed"),
        "auth": (r"AuthenticationError|Unauthorized|Forbidden", "Authentication/authorization failure"),
        "rate_limit": (r"RateLimit|TooManyRequests|429", "Rate limit exceeded"),
    }

    def __init__(self, repo_path: str = ""):
        self.repo_path = Path(repo_path) if repo_path else Path()
        self.incidents: dict[str, Incident] = {}
        self._mttr_history: list[float] = []

    def detect(self, title: str, description: str = "", source: str = "",
               severity: IncidentSeverity = IncidentSeverity.MEDIUM,
               affected: list[str] = None) -> Incident:
        iid = f"inc-{uuid.uuid4().hex[:12]}"
        incident = Incident(
            id=iid, title=title, severity=severity,
            source=source, description=description,
            affected_components=affected or [],
            detected_at=datetime.now(timezone.utc).isoformat(),
            timeline=[{"time": datetime.now(timezone.utc).isoformat(), "event": f"Incident detected: {title}"}],
        )
        self.incidents[iid] = incident
        return incident

    def classify_severity(self, error_message: str) -> IncidentSeverity:
        critical_patterns = ["data loss", "security breach", "system down", "crash", "panic", "outage"]
        high_patterns = ["unavailable", "timeout", "degraded", "error rate", "failure"]
        medium_patterns = ["warning", "retry", "slow", "partial"]

        msg_lower = error_message.lower()
        if any(p in msg_lower for p in critical_patterns):
            return IncidentSeverity.CRITICAL
        if any(p in msg_lower for p in high_patterns):
            return IncidentSeverity.HIGH
        if any(p in msg_lower for p in medium_patterns):
            return IncidentSeverity.MEDIUM
        return IncidentSeverity.LOW

    def collect_logs(self, incident: Incident, log_lines: list[str], max_logs: int = 50):
        for line in log_lines[:max_logs]:
            incident.logs.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "message": line[:500],
            })

    def analyze_root_cause(self, incident: Incident) -> str:
        log_text = "\n".join(l["message"] for l in incident.logs) + "\n" + incident.description

        for pattern_name, (pattern, description) in self.FAILURE_PATTERNS.items():
            import re
            if re.search(pattern, log_text, re.IGNORECASE):
                incident.root_cause = f"{pattern_name}: {description}"
                incident.timeline.append({
                    "time": datetime.now(timezone.utc).isoformat(),
                    "event": f"Root cause identified: {incident.root_cause}",
                })
                return incident.root_cause

        incident.root_cause = "Unknown — further investigation required"
        return incident.root_cause

    def recommend_fix(self, incident: Incident) -> str:
        rca = incident.root_cause.lower()

        fix_map = {
            "import_error": "Verify the package is installed in requirements.txt and import paths are correct",
            "syntax_error": "Review the latest code changes for syntax errors and run linter before deployment",
            "connection_error": "Check service availability, network configuration, and firewall rules",
            "timeout": "Increase timeout configuration, optimize the operation, or add retry logic",
            "memory": "Increase memory limit, optimize data structures, or add streaming/chunking",
            "permission": "Verify file permissions, IAM roles, and service account configurations",
            "value_error": "Add input validation and error handling for edge cases",
            "database": "Check database connectivity, connection pool, and query performance",
            "auth": "Verify API keys, tokens, and authentication middleware configuration",
            "rate_limit": "Implement exponential backoff, reduce request frequency, or request quota increase",
        }

        for key, fix in fix_map.items():
            if key in rca:
                incident.recommended_fix = fix
                incident.timeline.append({
                    "time": datetime.now(timezone.utc).isoformat(),
                    "event": f"Fix recommended: {fix[:80]}...",
                })
                return fix

        incident.recommended_fix = "Investigate logs and reproduce the issue in a staging environment"
        return incident.recommended_fix

    def resolve(self, incident: Incident) -> Incident:
        incident.status = IncidentStatus.RESOLVED
        incident.resolved_at = datetime.now(timezone.utc).isoformat()
        incident.fix_applied = True
        incident.timeline.append({
            "time": incident.resolved_at,
            "event": "Incident resolved",
        })
        detected = datetime.fromisoformat(incident.detected_at)
        resolved = datetime.fromisoformat(incident.resolved_at)
        incident.mttr_minutes = round((resolved - detected).total_seconds() / 60, 1)
        self._mttr_history.append(incident.mttr_minutes)
        return incident

    def generate_timeline(self, incident: Incident) -> list[dict]:
        return incident.timeline

    def generate_report(self) -> IncidentReport:
        active = [i for i in self.incidents.values() if i.status not in (IncidentStatus.RESOLVED, IncidentStatus.CLOSED)]
        resolved = [i for i in self.incidents.values() if i.status in (IncidentStatus.RESOLVED, IncidentStatus.CLOSED)]

        report = IncidentReport(
            repo_id=str(hash(str(self.repo_path))),
            repo_name=self.repo_path.name,
            timestamp=datetime.now(timezone.utc).isoformat(),
            active_incidents=active,
            resolved_incidents=resolved[-20:],
            total_incidents=len(self.incidents),
            critical_count=sum(1 for i in self.incidents.values() if i.severity == IncidentSeverity.CRITICAL),
            high_count=sum(1 for i in self.incidents.values() if i.severity == IncidentSeverity.HIGH),
            medium_count=sum(1 for i in self.incidents.values() if i.severity == IncidentSeverity.MEDIUM),
            low_count=sum(1 for i in self.incidents.values() if i.severity == IncidentSeverity.LOW),
        )

        if self._mttr_history:
            report.avg_mttr_minutes = round(sum(self._mttr_history) / len(self._mttr_history), 1)

        cause_counts = defaultdict(int)
        for i in self.incidents.values():
            if i.root_cause:
                cause = i.root_cause.split(":")[0]
                cause_counts[cause] += 1
        report.top_causes = [f"{cause} ({count})" for cause, count in
                            sorted(cause_counts.items(), key=lambda x: -x[1])[:5]]

        if report.critical_count > 0:
            report.recommendations.append(f"Investigate {report.critical_count} critical incidents immediately")
        if report.avg_mttr_minutes > 60:
            report.recommendations.append(f"High MTTR ({report.avg_mttr_minutes}min) — improve alerting and runbooks")
        if active:
            report.recommendations.append(f"Resolve {len(active)} active incidents")
        if report.top_causes:
            report.recommendations.append(f"Address root causes: {report.top_causes[0]}")

        return report

    def get_mttr_trend(self) -> list[float]:
        return self._mttr_history[-30:]
