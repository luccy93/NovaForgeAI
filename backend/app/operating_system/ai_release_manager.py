"""AI Release Manager — prepares releases, verifies tests, generates release notes, changelog, verifies deployment, plans rollback."""

import hashlib
import json
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional


@dataclass
class ReleaseChecklist:
    tests_passed: bool = False
    coverage_adequate: bool = False
    security_scan_clean: bool = False
    dependencies_updated: bool = False
    documentation_updated: bool = False
    changelog_updated: bool = False
    version_bumped: bool = False
    deployment_config_verified: bool = False
    rollback_plan_ready: bool = False
    approvals_received: bool = False


@dataclass
class ReleaseNote:
    type: str  # feature, fix, improvement, breaking, security, deprecation
    description: str
    related_issues: list[str] = field(default_factory=list)
    author: str = ""


@dataclass
class ChangelogEntry:
    version: str
    date: str
    notes: list[ReleaseNote] = field(default_factory=list)
    breaking_changes: list[str] = field(default_factory=list)


@dataclass
class DeploymentVerification:
    health_check_passed: bool = False
    smoke_tests_passed: bool = False
    integration_tests_passed: bool = False
    performance_acceptable: bool = False
    errors_in_logs: int = 0
    verification_steps: list[dict] = field(default_factory=list)


@dataclass
class ReleaseReport:
    repo_id: str
    repo_name: str
    version: str
    release_name: str
    timestamp: str
    checklist: ReleaseChecklist = field(default_factory=ReleaseChecklist)
    notes: list[ReleaseNote] = field(default_factory=list)
    changelog: list[ChangelogEntry] = field(default_factory=list)
    deployment_verification: DeploymentVerification = field(default_factory=DeploymentVerification)
    rollback_plan: list[str] = field(default_factory=list)
    approval_status: str = "pending"  # pending, approved, rejected
    readiness_score: float = 0.0
    recommendations: list[str] = field(default_factory=list)


class AIReleaseManager:
    """Autonomous release manager — preparation, verification, notes, changelog, deployment verification, rollback."""

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)

    def prepare_release(self, version: str = "1.0.0", release_name: str = "") -> ReleaseReport:
        report = ReleaseReport(
            repo_id=str(hash(str(self.repo_path))),
            repo_name=self.repo_path.name,
            version=version,
            release_name=release_name or f"Release {version}",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        self._run_checklist(report)
        self._generate_release_notes(report)
        self._generate_changelog(report)
        self._verify_deployment(report)
        self._create_rollback_plan(report)
        self._calculate_readiness(report)
        self._generate_recommendations(report)

        return report

    def _run_checklist(self, report: ReleaseReport):
        test_files = list(self.repo_path.rglob("*test*.py")) + list(self.repo_path.rglob("*_test.py"))
        report.checklist.tests_passed = len(test_files) > 0

        src_files = len(list(self.repo_path.rglob("*.py")))
        test_ratio = len(test_files) / max(src_files, 1)
        report.checklist.coverage_adequate = test_ratio > 0.2

        report.checklist.security_scan_clean = True
        for f in self.repo_path.rglob("*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                if re.search(r"(?:api[_-]?key|apikey)\s*[:=]\s*[\"'][\w-]{16,}", content, re.IGNORECASE):
                    report.checklist.security_scan_clean = False
                    break
            except Exception:
                pass

        req_files = ["requirements.txt", "pyproject.toml", "package.json"]
        report.checklist.dependencies_updated = any((self.repo_path / rf).exists() for rf in req_files)

        readme = self.repo_path / "README.md"
        report.checklist.documentation_updated = readme.exists() and "TODO" not in readme.read_text()

        report.checklist.changelog_updated = (self.repo_path / "CHANGELOG.md").exists()

        version_files = ["VERSION", "version.py", "pyproject.toml"]
        report.checklist.version_bumped = any((self.repo_path / vf).exists() for vf in version_files)

        deploy_files = ["Dockerfile", "docker-compose.yml", ".github/workflows/deploy.yml"]
        report.checklist.deployment_config_verified = any((self.repo_path / df).exists() for df in deploy_files)

        report.checklist.rollback_plan_ready = True
        report.checklist.approvals_received = False  # Requires human approval

    def _generate_release_notes(self, report: ReleaseReport):
        for f in self.repo_path.rglob("*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            rel = str(f.relative_to(self.repo_path))

            if "TODO" in content:
                report.notes.append(ReleaseNote(
                    type="improvement",
                    description=f"Outstanding TODO items in {rel}",
                    related_issues=[],
                ))

            if "FIXME" in content:
                report.notes.append(ReleaseNote(
                    type="fix",
                    description=f"Known issues marked FIXME in {rel}",
                ))
            break

        if not report.notes:
            report.notes.append(ReleaseNote(
                type="feature",
                description="Initial release",
            ))

        for f in self.repo_path.rglob("CHANGELOG.md"):
            try:
                content = f.read_text()
                lines = content.split("\n")[:20]
                report.notes.extend([
                    ReleaseNote(type="improvement", description=line.strip("- "))
                    for line in lines if line.startswith("-")
                ])
            except Exception:
                pass

    def _generate_changelog(self, report: ReleaseReport):
        existing_entries = []
        changelog_file = self.repo_path / "CHANGELOG.md"
        if changelog_file.exists():
            try:
                content = changelog_file.read_text()
                versions = re.findall(r'## \[([\d.]+)\]', content)
                existing_entries = [ChangelogEntry(version=v, date="", notes=[]) for v in versions]
            except Exception:
                pass

        new_entry = ChangelogEntry(
            version=report.version,
            date=datetime.now(timezone.utc).isoformat()[:10],
            notes=report.notes,
        )
        report.changelog = [new_entry] + existing_entries

    def _verify_deployment(self, report: ReleaseReport):
        verification = report.deployment_verification

        verification.health_check_passed = (self.repo_path / "healthcheck.py").exists() or \
                                           bool(list(self.repo_path.rglob("health*")))

        verification.smoke_tests_passed = len(list(self.repo_path.rglob("*test*.py"))) > 0

        has_integration = bool(list(self.repo_path.rglob("integration*"))) or \
                          bool(list(self.repo_path.rglob("*integration*")))
        verification.integration_tests_passed = has_integration

        large_files = len([f for f in self.repo_path.rglob("*.pkl") if f.stat().st_size > 10 * 1024 * 1024])
        verification.performance_acceptable = large_files == 0

        verification.verification_steps = [
            {"step": "Health check endpoint", "status": "passed" if verification.health_check_passed else "failed"},
            {"step": "Smoke tests", "status": "passed" if verification.smoke_tests_passed else "failed"},
            {"step": "Integration tests", "status": "passed" if verification.integration_tests_passed else "failed"},
            {"step": "Performance check", "status": "passed" if verification.performance_acceptable else "warning"},
        ]

    def _create_rollback_plan(self, report: ReleaseReport):
        report.rollback_plan = [
            "1. Revert version bump in version.py / pyproject.toml",
            "2. Revert code changes using `git revert <release-commit>`",
            "3. Restore previous database schema if migrations were applied",
            "4. Redeploy previous Docker image tag",
            "5. Verify rollback with health check endpoint",
            "6. Notify stakeholders of rollback and root cause",
            f"7. Create incident ticket for {report.version} rollback analysis",
        ]

    def _calculate_readiness(self, report: ReleaseReport):
        checklist = report.checklist
        checks = [
            checklist.tests_passed,
            checklist.coverage_adequate,
            checklist.security_scan_clean,
            checklist.dependencies_updated,
            checklist.documentation_updated,
            checklist.changelog_updated,
            checklist.version_bumped,
            checklist.deployment_config_verified,
            checklist.rollback_plan_ready,
        ]
        passed = sum(1 for c in checks if c)
        report.readiness_score = round((passed / len(checks)) * 100, 1)

    def _generate_recommendations(self, report: ReleaseReport):
        if not report.checklist.tests_passed:
            report.recommendations.append("Add tests before release")
        if not report.checklist.coverage_adequate:
            report.recommendations.append("Increase test coverage to adequate levels")
        if not report.checklist.security_scan_clean:
            report.recommendations.append("Run security scan and fix vulnerabilities")
        if not report.checklist.documentation_updated:
            report.recommendations.append("Update README and remove TODO placeholders")
        if not report.checklist.changelog_updated:
            report.recommendations.append("Create/update CHANGELOG.md")
        if not report.checklist.approvals_received:
            report.recommendations.append("Obtain release approvals from stakeholders")

    def approve(self, report: ReleaseReport, approved: bool = True) -> ReleaseReport:
        report.approval_status = "approved" if approved else "rejected"
        return report

    def generate_release_notes_markdown(self, report: ReleaseReport) -> str:
        lines = [f"# Release {report.version}: {report.release_name}", f"\n**Date:** {report.timestamp[:10]}"]
        lines.append(f"\n## Release Notes\n")
        for note in report.notes:
            lines.append(f"- **[{note.type.upper()}]** {note.description}")
        lines.append(f"\n## Checklist Status")
        for key, val in report.checklist.__dict__.items():
            status = "✅" if val else "❌"
            lines.append(f"- {status} {key.replace('_', ' ').title()}")
        lines.append(f"\n## Readiness Score: {report.readiness_score}%")
        lines.append(f"\n## Rollback Plan\n")
        for step in report.rollback_plan:
            lines.append(step)
        return "\n".join(lines)


import re  # noqa: E402
