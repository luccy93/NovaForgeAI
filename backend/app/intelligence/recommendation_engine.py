"""Recommendation Engine — structured engineering recommendations with problem, evidence, impact, confidence, effort, and rollback."""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


@dataclass
class Recommendation:
    id: str
    title: str
    problem: str
    evidence: str
    category: str  # architecture, security, performance, maintainability, testing, documentation, dependency, process
    affected_files: list[str] = field(default_factory=list)
    affected_functions: list[str] = field(default_factory=list)
    business_impact: str = ""
    engineering_impact: str = ""
    risk_level: str = "medium"  # low, medium, high, critical
    confidence_score: float = 0.0  # 0-1
    estimated_effort: str = ""  # hours, days, weeks
    estimated_effort_hours: float = 0.0
    suggested_fix: str = ""
    rollback_plan: str = ""
    priority_score: float = 0.0
    created_at: str = ""
    source: str = ""
    status: str = "open"  # open, in_progress, resolved, dismissed


@dataclass
class RecommendationReport:
    repo_id: str
    repo_name: str
    timestamp: str
    recommendations: list[Recommendation] = field(default_factory=list)
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    category_breakdown: dict[str, int] = field(default_factory=dict)
    top_priorities: list[Recommendation] = field(default_factory=list)
    total_effort_hours: float = 0.0


class RecommendationEngine:
    """Generates structured engineering recommendations with all required metadata."""

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)

    def analyze(self) -> RecommendationReport:
        report = RecommendationReport(
            repo_id=str(hash(str(self.repo_path))),
            repo_name=self.repo_path.name,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        self._recommend_architecture_improvements(report)
        self._recommend_security_fixes(report)
        self._recommend_performance_optimizations(report)
        self._recommend_maintainability_improvements(report)
        self._recommend_testing_improvements(report)
        self._recommend_documentation_improvements(report)
        self._recommend_dependency_upgrades(report)
        self._recommend_process_improvements(report)

        report.critical_count = sum(1 for r in report.recommendations if r.risk_level == "critical")
        report.high_count = sum(1 for r in report.recommendations if r.risk_level == "high")
        report.medium_count = sum(1 for r in report.recommendations if r.risk_level == "medium")
        report.low_count = sum(1 for r in report.recommendations if r.risk_level == "low")

        cat_counts = {}
        for r in report.recommendations:
            cat_counts[r.category] = cat_counts.get(r.category, 0) + 1
        report.category_breakdown = cat_counts

        sorted_recs = sorted(report.recommendations, key=lambda r: -r.priority_score)
        report.top_priorities = sorted_recs[:5]
        report.total_effort_hours = sum(r.estimated_effort_hours for r in report.recommendations)

        return report

    def _recommend_architecture_improvements(self, report: RecommendationReport):
        arch_files = list(self.repo_path.rglob("ARCHITECTURE*")) + list(self.repo_path.rglob("architecture*"))
        if not arch_files:
            report.recommendations.append(self._make_rec(
                title="Create architecture documentation",
                problem="No architecture documentation found — new team members lack system understanding",
                evidence=f"Repository at {self.repo_path} has no ARCHITECTURE.md or architecture/ directory",
                category="architecture",
                risk_level="medium",
                confidence=0.9,
                effort_hours=4,
                fix="Create ARCHITECTURE.md with system overview, component diagram, data flow, and deployment architecture",
                rollback="Remove ARCHITECTURE.md if not needed",
            ))

        for f in self.repo_path.rglob("*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                lines = content.count("\n") + 1
            except Exception:
                continue
            if lines > 2000:
                rel = str(f.relative_to(self.repo_path))
                report.recommendations.append(self._make_rec(
                    title=f"Split monolithic module: {rel}",
                    problem=f"Module has {lines} lines — violates Single Responsibility Principle and hinders maintainability",
                    evidence=f"File {rel} contains {lines} lines of code, exceeding the recommended 500-line maximum",
                    category="architecture",
                    affected_files=[rel],
                    risk_level="high",
                    confidence=0.85,
                    effort_hours=lines / 100,
                    fix=f"Split {rel} into smaller modules by concern. Create separate files for each logical group",
                    rollback="Restore the original module from version control",
                ))
                break

        # Architecture drift detection
        has_container = any((self.repo_path / d).exists() for d in ["Dockerfile", "docker-compose.yml"])
        has_orchestration = any((self.repo_path / d).exists() for d in ["k8s", "helm", "terraform"])
        if has_container and not has_orchestration:
            report.recommendations.append(self._make_rec(
                title="Add container orchestration configuration",
                problem="Docker configuration exists but no orchestration — scaling requires manual intervention",
                evidence="Dockerfile found but no Kubernetes or Terraform configuration detected",
                category="architecture",
                risk_level="medium",
                confidence=0.7,
                effort_hours=8,
                fix="Add Kubernetes manifests (deployment.yaml, service.yaml, ingress.yaml) or Terraform modules",
                rollback="Remove orchestration configs, revert to docker-compose",
            ))

    def _recommend_security_fixes(self, report: RecommendationReport):
        secrets_patterns = {
            "API key": r"(?:api[_-]?key|apikey)\s*[:=]\s*[\"']?[\w-]{16,}",
            "Password": r"password\s*[:=]\s*[\"'][^\"']{6,}",
            "Private Key": r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----",
        }

        for secret_type, pattern in secrets_patterns.items():
            for f in self.repo_path.rglob("*"):
                if f.suffix not in (".py", ".js", ".ts", ".go", ".rs", ".java", ".env"):
                    continue
                try:
                    content = f.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                if re.search(pattern, content, re.IGNORECASE):
                    rel = str(f.relative_to(self.repo_path))
                    report.recommendations.append(self._make_rec(
                        title=f"Remove exposed {secret_type} in {rel}",
                        problem=f"Potential {secret_type.lower()} exposed in source code — immediate security risk",
                        evidence=f"Found matching pattern for {secret_type} in {rel}",
                        category="security",
                        affected_files=[rel],
                        risk_level="critical" if secret_type == "Private Key" else "high",
                        confidence=0.95,
                        effort_hours=0.5,
                        fix=f"Remove the {secret_type.lower()} from code. Use environment variables or a secrets manager like HashiCorp Vault",
                        rollback="Restore the secret from version control (if already committed, rotate it immediately)",
                    ))
                    break

    def _recommend_performance_optimizations(self, report: RecommendationReport):
        for f in self.repo_path.rglob("*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            rel = str(f.relative_to(self.repo_path))

            if re.search(r'for\s+\w+\s+in\s+.*:\s*\n\s+for\s+\w+\s+in\s+', content):
                report.recommendations.append(self._make_rec(
                    title=f"Optimize nested loops in {rel}",
                    problem="Nested loops cause O(n²) time complexity — performance degrades with data size",
                    evidence=f"Found nested loop pattern in {rel}",
                    category="performance",
                    affected_files=[rel],
                    risk_level="medium",
                    confidence=0.75,
                    effort_hours=2,
                    fix="Replace nested loops with dictionary lookups, set operations, or vectorized operations",
                    rollback="Revert to original nested loop implementation",
                ))
                break

    def _recommend_maintainability_improvements(self, report: RecommendationReport):
        for f in self.repo_path.rglob("*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                lines = content.count("\n") + 1
            except Exception:
                continue
            if lines > 500:
                rel = str(f.relative_to(self.repo_path))
                report.recommendations.append(self._make_rec(
                    title=f"Refactor large file: {rel}",
                    problem=f"File has {lines} lines — difficult to navigate, review, and maintain",
                    evidence=f"{rel} contains {lines} lines of code (recommended: <500)",
                    category="maintainability",
                    affected_files=[rel],
                    risk_level="medium",
                    confidence=0.8,
                    effort_hours=lines / 100,
                    fix=f"Split {rel} into smaller modules by functionality or concern (aim for <300 lines per module)",
                    rollback="Restore original file from version control",
                ))
                break

    def _recommend_testing_improvements(self, report: RecommendationReport):
        test_files = list(self.repo_path.rglob("*test*.py")) + list(self.repo_path.rglob("*_test.py"))
        src_files = list(self.repo_path.rglob("*.py"))

        actual_src = [f for f in src_files if "test" not in f.name.lower() and f.name != "__init__.py"]
        if len(test_files) < max(len(actual_src) * 0.2, 1):
            report.recommendations.append(self._make_rec(
                title="Increase test coverage significantly",
                problem=f"Only {len(test_files)} test files for {len(actual_src)} source files — insufficient coverage",
                evidence=f"Test-to-source file ratio: {len(test_files)}/{len(actual_src)} ({len(test_files)/max(len(actual_src),1)*100:.0f}%)",
                category="testing",
                risk_level="high",
                confidence=0.85,
                effort_hours=max(len(actual_src) * 0.5, 8),
                fix="Add unit tests for all public functions. Target minimum 1:3 test-to-source file ratio. Include edge cases and error paths",
                rollback="Remove test files if they introduce false positives",
            ))

    def _recommend_documentation_improvements(self, report: RecommendationReport):
        readme = self.repo_path / "README.md"
        if not readme.exists():
            report.recommendations.append(self._make_rec(
                title="Create README.md",
                problem="No README — new developers and users cannot understand the project",
                evidence="README.md not found in repository root",
                category="documentation",
                risk_level="high",
                confidence=0.95,
                effort_hours=2,
                fix="Create README.md with: project description, installation guide, usage examples, API docs, and contribution guide",
                rollback="Remove README.md",
            ))
        else:
            content = readme.read_text(encoding="utf-8", errors="ignore")
            required_sections = ["installation", "usage", "api", "contributing", "license"]
            missing = [s for s in required_sections if s not in content.lower()]
            if missing:
                report.recommendations.append(self._make_rec(
                    title=f"Add missing README sections: {', '.join(missing)}",
                    problem=f"README is missing essential sections: {', '.join(missing)}",
                    evidence=f"README.md exists but lacks: {', '.join(missing)}",
                    category="documentation",
                    risk_level="medium",
                    confidence=0.8,
                    effort_hours=len(missing) * 0.5,
                    fix=f"Add the following sections to README.md: {', '.join(missing)}",
                    rollback="Remove added sections",
                ))

    def _recommend_dependency_upgrades(self, report: RecommendationReport):
        req_files = list(self.repo_path.glob("requirements.txt"))
        for rf in req_files:
            try:
                lines = rf.read_text().splitlines()
            except Exception:
                continue

            outdated = []
            known_versions = {
                "flask": "3.1.0", "fastapi": "0.115.0", "django": "5.1.0",
                "pydantic": "2.9.0", "requests": "2.32.0", "httpx": "0.27.2",
                "sqlalchemy": "2.0.35", "alembic": "1.13.2", "celery": "5.4.0",
            }

            for line in lines:
                if "==" in line:
                    pkg, ver = line.split("==", 1)
                    pkg = pkg.strip().lower()
                    ver = ver.strip()
                    if pkg in known_versions and ver != known_versions[pkg]:
                        outdated.append(f"{pkg} ({ver} → {known_versions[pkg]})")

            if outdated:
                report.recommendations.append(self._make_rec(
                    title=f"Update {len(outdated)} outdated dependencies",
                    problem=f"{len(outdated)} dependencies are outdated — missing bug fixes, performance improvements, and security patches",
                    evidence=f"Outdated packages: {', '.join(outdated[:5])}",
                    category="dependency",
                    risk_level="medium",
                    confidence=0.8,
                    effort_hours=len(outdated) * 0.5,
                    fix=f"Update packages: {', '.join(outdated[:5])}. Run tests after each upgrade to detect breaking changes",
                    rollback="Revert requirements.txt to previous versions",
                ))

    def _recommend_process_improvements(self, report: RecommendationReport):
        if not (self.repo_path / ".github/workflows").exists() and \
           not (self.repo_path / ".gitlab-ci.yml").exists() and \
           not list(self.repo_path.rglob("Jenkinsfile")):
            report.recommendations.append(self._make_rec(
                title="Set up CI/CD pipeline",
                problem="No CI/CD pipeline — manual builds and deployments are error-prone and time-consuming",
                evidence="No CI configuration found (.github/workflows, .gitlab-ci.yml, Jenkinsfile)",
                category="process",
                risk_level="high",
                confidence=0.9,
                effort_hours=4,
                fix="Set up GitHub Actions workflow: run tests on PR, build Docker image, deploy to staging on merge to main",
                rollback="Disable or remove CI workflow files",
            ))

        if not (self.repo_path / "CONTRIBUTING.md").exists():
            report.recommendations.append(self._make_rec(
                title="Create CONTRIBUTING.md",
                problem="No contribution guidelines — inconsistent PR quality and onboarding friction",
                evidence="CONTRIBUTING.md not found in repository root",
                category="process",
                risk_level="low",
                confidence=0.85,
                effort_hours=1,
                fix="Create CONTRIBUTING.md with: branch strategy, PR process, code style guide, testing requirements, review expectations",
                rollback="Remove CONTRIBUTING.md",
            ))

    def _make_rec(self, title: str, problem: str, evidence: str, category: str,
                  risk_level: str, confidence: float, effort_hours: float,
                  fix: str, rollback: str = "", affected_files: list = None) -> Recommendation:
        rid = hashlib.sha256(f"{title}:{datetime.now(timezone.utc).isoformat()}".encode()).hexdigest()[:16]

        impact_map = {
            "critical": "Immediate business risk — requires urgent attention",
            "high": "Significant engineering or business impact",
            "medium": "Moderate impact on productivity or quality",
            "low": "Minor improvement opportunity",
        }

        effort_map = {
            0: "minutes", 0.5: "30 minutes", 1: "1 hour", 2: "2 hours",
            4: "4 hours (half day)", 8: "1 day", 40: "1 week", 160: "1 month",
        }
        effort_str = "custom"
        for k in sorted(effort_map.keys(), reverse=True):
            if effort_hours >= k:
                effort_str = effort_map[k]
                break

        extra = max(0, effort_hours * 0.2)
        risk_penalty = {"low": 0.5, "medium": 1.0, "high": 2.0, "critical": 4.0}
        priority = confidence * 10 + risk_penalty.get(risk_level, 1.0) * 3 - effort_hours * 0.1 + extra
        priority = max(0, min(20, priority))

        return Recommendation(
            id=rid,
            title=title,
            problem=problem,
            evidence=evidence,
            category=category,
            affected_files=affected_files or [],
            business_impact=impact_map.get(risk_level, "Needs assessment"),
            engineering_impact=problem,
            risk_level=risk_level,
            confidence_score=round(confidence, 2),
            estimated_effort=effort_str,
            estimated_effort_hours=effort_hours,
            suggested_fix=fix,
            rollback_plan=rollback or f"Revert changes related to '{title}' using version control",
            priority_score=round(priority, 1),
            created_at=datetime.now(timezone.utc).isoformat(),
            source="recommendation_engine",
        )


import re  # noqa: E402
