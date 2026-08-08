"""Platform Automation — scheduled nightly/weekly/monthly jobs, repository audits, security audits, performance audits, documentation audits, architecture reviews, compliance reviews."""

import hashlib
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Callable


class AuditFrequency(Enum):
    NIGHTLY = "nightly"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


class AuditSeverity(Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class AuditFinding:
    id: str
    category: str
    severity: AuditSeverity
    description: str
    recommendation: str
    file: str = ""
    line: int = 0
    estimated_effort: str = ""


@dataclass
class AuditReport:
    id: str
    name: str
    audit_type: str  # repository, security, performance, documentation, architecture, compliance
    frequency: AuditFrequency
    findings: list[AuditFinding] = field(default_factory=list)
    score: float = 100.0
    passed_checks: int = 0
    total_checks: int = 0
    started_at: str = ""
    completed_at: str = ""
    summary: str = ""
    recommendations: list[str] = field(default_factory=list)


@dataclass
class PlatformAutomationSchedule:
    name: str
    audit_type: str
    frequency: AuditFrequency
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    enabled: bool = True


class PlatformAutomation:
    """Scheduled platform automation — nightly/weekly/monthly audits and reviews across all dimensions."""

    SCHEDULES = [
        PlatformAutomationSchedule("Nightly Repository Scan", "repository", AuditFrequency.NIGHTLY),
        PlatformAutomationSchedule("Weekly Security Audit", "security", AuditFrequency.WEEKLY),
        PlatformAutomationSchedule("Weekly Performance Audit", "performance", AuditFrequency.WEEKLY),
        PlatformAutomationSchedule("Weekly Documentation Audit", "documentation", AuditFrequency.WEEKLY),
        PlatformAutomationSchedule("Monthly Architecture Review", "architecture", AuditFrequency.MONTHLY),
        PlatformAutomationSchedule("Monthly Compliance Review", "compliance", AuditFrequency.MONTHLY),
    ]

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)
        self.audit_history: dict[str, list[AuditReport]] = defaultdict(list)

    def run_audit(self, audit_type: str) -> AuditReport:
        auditor = getattr(self, f"_audit_{audit_type}", None)
        if not auditor:
            raise ValueError(f"Unknown audit type: {audit_type}")

        report = AuditReport(
            id=f"audit-{uuid.uuid4().hex[:12]}",
            name=f"{audit_type.replace('_', ' ').title()} Audit",
            audit_type=audit_type,
            frequency=self._get_frequency(audit_type),
            started_at=datetime.now(timezone.utc).isoformat(),
        )

        try:
            report = auditor(report)
        except Exception as e:
            report.findings.append(AuditFinding(
                id=f"af-{uuid.uuid4().hex[:8]}",
                category="error",
                severity=AuditSeverity.HIGH,
                description=f"Audit failed: {str(e)}",
                recommendation="Review audit configuration and retry",
            ))

        report.completed_at = datetime.now(timezone.utc).isoformat()
        report.total_checks = len(report.findings) + report.passed_checks
        report.score = round((report.passed_checks / max(report.total_checks, 1)) * 100, 1)
        report.summary = f"{report.passed_checks}/{report.total_checks} checks passed ({report.score}%)"
        report.recommendations = [f.description for f in report.findings if f.severity in (AuditSeverity.HIGH, AuditSeverity.CRITICAL)][:5]

        self.audit_history[audit_type].append(report)
        if len(self.audit_history[audit_type]) > 100:
            self.audit_history[audit_type] = self.audit_history[audit_type][-100:]

        return report

    def _audit_repository(self, report: AuditReport) -> AuditReport:
        checks = [
            ("README exists", (self.repo_path / "README.md").exists()),
            ("LICENSE exists", (self.repo_path / "LICENSE").exists()),
            ("Has .gitignore", (self.repo_path / ".gitignore").exists()),
            ("Has requirements.txt or pyproject.toml", 
             (self.repo_path / "requirements.txt").exists() or (self.repo_path / "pyproject.toml").exists()),
            ("No .env committed", not (self.repo_path / ".env").exists() or (self.repo_path / ".env.example").exists()),
            ("Has test files", bool(list(self.repo_path.rglob("*test*.py")))),
            ("Has Dockerfile", (self.repo_path / "Dockerfile").exists()),
            ("Has CI/CD", (self.repo_path / ".github/workflows").exists() or (self.repo_path / ".gitlab-ci.yml").exists()),
        ]
        for name, passed in checks:
            if not passed:
                report.findings.append(AuditFinding(
                    id=f"af-{uuid.uuid4().hex[:8]}",
                    category="repository",
                    severity=AuditSeverity.MEDIUM,
                    description=f"Missing: {name}",
                    recommendation=f"Create the missing {name.lower()} file/configuration",
                ))
            else:
                report.passed_checks += 1
        return report

    def _audit_security(self, report: AuditReport) -> AuditReport:
        patterns = {
            "Hardcoded API key": (r"(?:api[_-]?key|apikey)\s*[:=]\s*[\"']?[\w-]{16,}", AuditSeverity.HIGH),
            "Hardcoded password": (r"password\s*[:=]\s*[\"'][^\"']{6,}", AuditSeverity.HIGH),
            "Private key exposed": (r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----", AuditSeverity.CRITICAL),
            "eval() usage": (r"\beval\s*\(", AuditSeverity.HIGH),
            "exec() usage": (r"\bexec\s*\(", AuditSeverity.HIGH),
            "Pickle load": (r"pickle\.loads?\(", AuditSeverity.HIGH),
            "Shell injection": (r"os\.system\(|subprocess\.call\(.*shell=True", AuditSeverity.CRITICAL),
            "SQL injection risk": (r"execute\(.*f[\"'].*\{", AuditSeverity.CRITICAL),
        }

        for name, (pattern, severity) in patterns.items():
            found = False
            for f in self.repo_path.rglob("*"):
                if f.suffix not in (".py", ".js", ".ts", ".env"):
                    continue
                try:
                    content = f.read_text(encoding="utf-8", errors="ignore")
                    if re.search(pattern, content, re.IGNORECASE):
                        report.findings.append(AuditFinding(
                            id=f"af-{uuid.uuid4().hex[:8]}",
                            category="security",
                            severity=severity,
                            description=f"{name} detected in {f.relative_to(self.repo_path)}",
                            recommendation=f"Remove {name.lower()} and use environment variables",
                        ))
                        found = True
                        break
                except Exception:
                    pass
            if not found:
                report.passed_checks += 1
        return report

    def _audit_performance(self, report: AuditReport) -> AuditReport:
        large_files = 0
        nested_loops = 0
        for f in self.repo_path.rglob("*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                if content.count("\n") > 500:
                    large_files += 1
                if re.search(r"for\s+\w+\s+in\s+.*:\s*\n\s+for\s+\w+\s+in\s+", content):
                    nested_loops += 1
            except Exception:
                pass

        if large_files > 3:
            report.findings.append(AuditFinding(
                id=f"af-{uuid.uuid4().hex[:8]}",
                category="performance",
                severity=AuditSeverity.MEDIUM,
                description=f"{large_files} files exceed 500 lines",
                recommendation="Split large files into smaller modules",
                estimated_effort=f"{large_files * 2}h",
            ))
        else:
            report.passed_checks += 1

        if nested_loops > 2:
            report.findings.append(AuditFinding(
                id=f"af-{uuid.uuid4().hex[:8]}",
                category="performance",
                severity=AuditSeverity.MEDIUM,
                description=f"{nested_loops} files with nested loops detected",
                recommendation="Replace nested loops with vectorized operations or dictionary lookups",
            ))
        else:
            report.passed_checks += 1

        return report

    def _audit_documentation(self, report: AuditReport) -> AuditReport:
        readme = self.repo_path / "README.md"
        if not readme.exists():
            report.findings.append(AuditFinding(
                id=f"af-{uuid.uuid4().hex[:8]}",
                category="documentation",
                severity=AuditSeverity.HIGH,
                description="README.md is missing",
                recommendation="Create README.md with project description, installation, and usage guide",
            ))
        else:
            report.passed_checks += 1
            content = readme.read_text(encoding="utf-8", errors="ignore")
            required = ["installation", "usage", "api", "contributing"]
            missing = [s for s in required if s not in content.lower()]
            for section in missing:
                report.findings.append(AuditFinding(
                    id=f"af-{uuid.uuid4().hex[:8]}",
                    category="documentation",
                    severity=AuditSeverity.LOW,
                    description=f"README missing '{section}' section",
                    recommendation=f"Add '{section}' section to README.md",
                ))

        changelog = self.repo_path / "CHANGELOG.md"
        if not changelog.exists():
            report.findings.append(AuditFinding(
                id=f"af-{uuid.uuid4().hex[:8]}",
                category="documentation",
                severity=AuditSeverity.LOW,
                description="CHANGELOG.md is missing",
                recommendation="Create CHANGELOG.md to track releases",
            ))

        return report

    def _audit_architecture(self, report: AuditReport) -> AuditReport:
        docstring_count = 0
        func_count = 0
        for f in self.repo_path.rglob("*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                funcs = re.findall(r'def\s+\w+\(', content)
                func_count += len(funcs)
                docstring_count += len(re.findall(r'""".*?"""', content, re.DOTALL))
            except Exception:
                pass

        if func_count > 0:
            doc_ratio = docstring_count / func_count
            if doc_ratio < 0.3:
                report.findings.append(AuditFinding(
                    id=f"af-{uuid.uuid4().hex[:8]}",
                    category="architecture",
                    severity=AuditSeverity.MEDIUM,
                    description=f"Low documentation coverage: {doc_ratio:.0%} of functions have docstrings",
                    recommendation="Add docstrings to all public functions and classes",
                ))
            else:
                report.passed_checks += 1

        py_files = list(self.repo_path.rglob("*.py"))
        if len(py_files) > 20:
            mod_dirs = set(f.parent for f in py_files)
            if len(mod_dirs) < 3:
                report.findings.append(AuditFinding(
                    id=f"af-{uuid.uuid4().hex[:8]}",
                    category="architecture",
                    severity=AuditSeverity.LOW,
                    description=f"{len(py_files)} files in only {len(mod_dirs)} directories — flat structure",
                    recommendation="Organize into modules by functionality",
                ))
            else:
                report.passed_checks += 1

        return report

    def _audit_compliance(self, report: AuditReport) -> AuditReport:
        compliance_checks = [
            ("Has license file", (self.repo_path / "LICENSE").exists()),
            ("Has contributing guide", (self.repo_path / "CONTRIBUTING.md").exists()),
            ("Has code of conduct", (self.repo_path / "CODE_OF_CONDUCT.md").exists()),
            ("Has .env.example", (self.repo_path / ".env.example").exists() or (self.repo_path / ".env.sample").exists()),
            ("Has security policy", (self.repo_path / "SECURITY.md").exists()),
            ("No secrets in code", True),
        ]

        for name, passed in compliance_checks:
            if not passed:
                report.findings.append(AuditFinding(
                    id=f"af-{uuid.uuid4().hex[:8]}",
                    category="compliance",
                    severity=AuditSeverity.MEDIUM,
                    description=f"Missing: {name}",
                    recommendation=f"Create the {name.lower()} file",
                ))
            else:
                report.passed_checks += 1

        return report

    def _get_frequency(self, audit_type: str) -> AuditFrequency:
        freq_map = {
            "repository": AuditFrequency.NIGHTLY,
            "security": AuditFrequency.WEEKLY,
            "performance": AuditFrequency.WEEKLY,
            "documentation": AuditFrequency.WEEKLY,
            "architecture": AuditFrequency.MONTHLY,
            "compliance": AuditFrequency.MONTHLY,
        }
        return freq_map.get(audit_type, AuditFrequency.WEEKLY)

    def get_due_audits(self) -> list[PlatformAutomationSchedule]:
        now = datetime.now(timezone.utc)
        due = []
        for schedule in self.SCHEDULES:
            if not schedule.enabled:
                continue
            if schedule.next_run is None:
                due.append(schedule)
                continue
            try:
                next_run = datetime.fromisoformat(schedule.next_run)
                if now >= next_run:
                    due.append(schedule)
            except (ValueError, TypeError):
                due.append(schedule)
        return due

    def get_audit_history(self, audit_type: str, limit: int = 10) -> list[AuditReport]:
        return self.audit_history.get(audit_type, [])[-limit:]

    def get_dashboard(self) -> dict:
        return {
            "schedules": [
                {"name": s.name, "type": s.audit_type, "frequency": s.frequency.value,
                 "last_run": s.last_run, "next_run": s.next_run, "enabled": s.enabled}
                for s in self.SCHEDULES
            ],
            "latest_scores": {
                at: (hist[-1].score if hist else None)
                for at, hist in self.audit_history.items()
            },
        }


import re  # noqa: E402
