"""AI Project Manager — analyzes repositories, identifies missing work, generates backlog, creates issues, estimates complexity and timelines, suggests releases."""

import hashlib
import json
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional


@dataclass
class BacklogItem:
    id: str
    title: str
    description: str
    source: str  # repo_analysis, missing_test, missing_doc, tech_debt, security, performance
    complexity: str  # low, medium, high, critical
    priority_score: float = 0.0
    estimated_hours: float = 0.0
    suggested_assignee: str = ""
    related_files: list[str] = field(default_factory=list)
    issue_type: str = "task"  # bug, feature, improvement, chore


@dataclass
class ComplexityEstimate:
    file: str
    function: str
    complexity: str
    score: int
    reasoning: str


@dataclass
class TimelineEstimate:
    total_tasks: int
    estimated_hours: float
    estimated_days: float
    developers_needed: int
    confidence: float
    risk_factors: list[str] = field(default_factory=list)


@dataclass
class ReleaseSuggestion:
    version: str
    name: str
    features: list[str]
    fixes: list[str]
    improvements: list[str]
    estimated_date: str
    confidence: float


@dataclass
class ProjectManagerReport:
    repo_id: str
    repo_name: str
    timestamp: str
    backlog: list[BacklogItem] = field(default_factory=list)
    complexity_estimates: list[ComplexityEstimate] = field(default_factory=list)
    timeline: Optional[TimelineEstimate] = None
    release_roadmap: list[ReleaseSuggestion] = field(default_factory=list)
    github_issues: list[dict] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


class AIProjectManager:
    """Autonomous project manager — analyzes repos, generates backlog, estimates, plans releases."""

    COMPLEXITY_PATTERNS = {
        "low": (r"def\s+\w+\(.*\):\s*\n\s+(?:return|pass|print)", 1),
        "medium": (r"(?:if|for|while|try)", 3),
        "high": (r"(?:for.*:.*\n\s+for|while.*:.*\n\s+while|if.*:.*\n\s+if.*:.*\n\s+if)", 6),
        "critical": (r"(?:except|finally|with\s+.*\s+as|async|await)", 9),
    }

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)

    def analyze(self) -> ProjectManagerReport:
        report = ProjectManagerReport(
            repo_id=str(hash(str(self.repo_path))),
            repo_name=self.repo_path.name,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        self._generate_backlog(report)
        self._estimate_complexity(report)
        self._estimate_timeline(report)
        self._suggest_releases(report)
        self._generate_recommendations(report)

        return report

    def _generate_backlog(self, report: ProjectManagerReport):
        # Missing tests
        test_files = list(self.repo_path.rglob("*test*.py")) + list(self.repo_path.rglob("*_test.py"))
        src_files = [f for f in self.repo_path.rglob("*.py") if "test" not in f.name.lower() and f.name != "__init__.py"]

        for sf in src_files[:20]:
            rel = str(sf.relative_to(self.repo_path))
            has_test = any(tf.name.startswith(f"test_{sf.stem}") or tf.name.endswith(f"{sf.stem}_test.py")
                           for tf in test_files)
            if not has_test:
                report.backlog.append(BacklogItem(
                    id=f"bl-{uuid.uuid4().hex[:8]}",
                    title=f"Write tests for {rel}",
                    description=f"Module {rel} has no corresponding test file. Create unit tests covering main functions.",
                    source="missing_test",
                    complexity="medium",
                    priority_score=5.0,
                    estimated_hours=2.0,
                    related_files=[rel],
                    issue_type="improvement",
                ))

        # Missing documentation
        readme = self.repo_path / "README.md"
        if not readme.exists():
            report.backlog.append(BacklogItem(
                id=f"bl-{uuid.uuid4().hex[:8]}",
                title="Create README.md",
                description="Project is missing a README.md. Create one with project description, installation guide, and usage examples.",
                source="missing_doc",
                complexity="low",
                priority_score=8.0,
                estimated_hours=2.0,
                issue_type="improvement",
            ))

        # Technical debt from TODO/FIXME
        for f in self.repo_path.rglob("*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            rel = str(f.relative_to(self.repo_path))
            todos = re.findall(r'#\s*(TODO|FIXME|HACK|XXX)\s*:\s*(.+)', content)
            for todo_type, desc in todos[:5]:
                report.backlog.append(BacklogItem(
                    id=f"bl-{uuid.uuid4().hex[:8]}",
                    title=f"{todo_type}: {desc[:80]}",
                    description=f"Found in {rel}. {desc}",
                    source="tech_debt",
                    complexity="medium" if todo_type in ("FIXME", "HACK") else "low",
                    priority_score=4.0,
                    estimated_hours=1.0,
                    related_files=[rel],
                    issue_type="chore",
                ))

        # Security issues
        security_patterns = {
            "Hardcoded API key": (r"(?:api[_-]?key|apikey)\s*[:=]\s*[\"'][\w-]{16,}", "high", 8.0),
            "eval/exec usage": (r"\b(?:eval|exec)\s*\(", "high", 6.0),
            "Pickle deserialization": (r"pickle\.loads?\(", "high", 7.0),
            "SQL injection risk": (r"execute\(.*f[\"'].*\{", "critical", 9.0),
        }
        for f in self.repo_path.rglob("*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            rel = str(f.relative_to(self.repo_path))
            for name, (pattern, complexity, score) in security_patterns.items():
                if re.search(pattern, content, re.IGNORECASE):
                    report.backlog.append(BacklogItem(
                        id=f"bl-{uuid.uuid4().hex[:8]}",
                        title=f"Fix {name} in {rel}",
                        description=f"Security issue detected in {rel}: {name}",
                        source="security",
                        complexity=complexity,
                        priority_score=score,
                        estimated_hours=1.0 if complexity != "critical" else 3.0,
                        related_files=[rel],
                        issue_type="bug",
                    ))
                    break

        # Large files needing refactoring
        for f in self.repo_path.rglob("*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                lines = content.count("\n") + 1
            except Exception:
                continue
            if lines > 500:
                rel = str(f.relative_to(self.repo_path))
                report.backlog.append(BacklogItem(
                    id=f"bl-{uuid.uuid4().hex[:8]}",
                    title=f"Refactor large file: {rel} ({lines} lines)",
                    description=f"Module is {lines} lines. Split into smaller modules for better maintainability.",
                    source="tech_debt",
                    complexity="high",
                    priority_score=min(10, lines / 200) * 2,
                    estimated_hours=lines / 100,
                    related_files=[rel],
                    issue_type="improvement",
                ))
                break

    def _estimate_complexity(self, report: ProjectManagerReport):
        for f in self.repo_path.rglob("*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                tree = compile(content, f.name, "exec", ast.PyCF_ONLY_AST)
            except Exception:
                continue

            rel = str(f.relative_to(self.repo_path))
            funcs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]

            for func in funcs:
                func_content = content[func.lineno:getattr(func, 'end_lineno', func.lineno)]
                for name, (pattern, score) in self.COMPLEXITY_PATTERNS.items():
                    if re.search(pattern, func_content):
                        report.complexity_estimates.append(ComplexityEstimate(
                            file=rel,
                            function=func.name,
                            complexity=name,
                            score=score,
                            reasoning=f"Contains pattern matching '{name}' complexity",
                        ))
                        break

    def _estimate_timeline(self, report: ProjectManagerReport):
        total_hours = sum(item.estimated_hours for item in report.backlog)
        complexity_factors = {"low": 1, "medium": 2, "high": 4, "critical": 8}

        weighted_hours = sum(
            item.estimated_hours * complexity_factors.get(item.complexity, 2)
            for item in report.backlog
        )

        developers = max(1, round(len(report.backlog) / 15))
        daily_hours = developers * 4  # assume 4 productive hours/day
        days = weighted_hours / max(daily_hours, 1)
        confidence = max(0.3, min(0.9, 1 - (len(report.backlog) * 0.02)))

        risk_factors = []
        if len(report.backlog) > 20:
            risk_factors.append("Large backlog — may need prioritization")
        if any(i.complexity == "critical" for i in report.backlog):
            risk_factors.append("Critical items require immediate attention")
        if developers == 1:
            risk_factors.append("Single developer — bus factor risk")

        report.timeline = TimelineEstimate(
            total_tasks=len(report.backlog),
            estimated_hours=round(total_hours, 1),
            estimated_days=round(days, 1),
            developers_needed=developers,
            confidence=round(confidence, 2),
            risk_factors=risk_factors,
        )

    def _suggest_releases(self, report: ProjectManagerReport):
        now = datetime.now(timezone.utc)

        features = [b for b in report.backlog if b.issue_type == "feature"]
        fixes = [b for b in report.backlog if b.issue_type == "bug"]
        improvements = [b for b in report.backlog if b.issue_type == "improvement"]

        if features or fixes or improvements:
            v1_hours = sum(b.estimated_hours for b in (fixes[:5] + improvements[:3]))
            v1_days = v1_hours / 4
            report.release_roadmap.append(ReleaseSuggestion(
                version="1.0.0",
                name="Initial Release",
                features=[b.title for b in features[:3]],
                fixes=[b.title for b in fixes[:3]],
                improvements=[b.title for b in improvements[:3]],
                estimated_date=(now + timedelta(days=v1_days)).isoformat()[:10],
                confidence=0.6,
            ))

            if len(improvements) > 3:
                remaining = improvements[3:6]
                v2_hours = sum(b.estimated_hours for b in remaining)
                v2_days = v2_hours / 4
                report.release_roadmap.append(ReleaseSuggestion(
                    version="1.1.0",
                    name="Quality & Reliability",
                    features=[],
                    fixes=[b.title for b in fixes[3:5]] if len(fixes) > 3 else [],
                    improvements=[b.title for b in remaining],
                    estimated_date=(now + timedelta(days=v1_days + v2_days)).isoformat()[:10],
                    confidence=0.5,
                ))

    def _generate_recommendations(self, report: ProjectManagerReport):
        if report.backlog:
            critical = [b for b in report.backlog if b.complexity == "critical"]
            if critical:
                report.recommendations.append(f"Address {len(critical)} critical items immediately: {critical[0].title}")
            report.recommendations.append(f"Sprint planning: prioritize {len(report.backlog)} backlog items")
            report.recommendations.append(f"Allocate {report.timeline.estimated_days if report.timeline else 5} days for initial fixes")

        if report.timeline and report.timeline.developers_needed > 2:
            report.recommendations.append(f"Team of {report.timeline.developers_needed} developers recommended for estimated workload")

        if report.complexity_estimates:
            high_complexity = [c for c in report.complexity_estimates if c.complexity in ("high", "critical")]
            if high_complexity:
                report.recommendations.append(f"Review {len(high_complexity)} high-complexity functions for refactoring")


import ast  # noqa: E402
