"""Predictive Engineering — ML-informed predictions for build failures, merge conflicts, regressions, security risks, and instability."""

import hashlib
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional


@dataclass
class Prediction:
    id: str
    category: str  # build_failure, merge_conflict, deployment_failure, performance_regression, security_risk, repo_instability, tech_debt_growth, dependency_failure
    description: str
    probability: float  # 0-1
    confidence: float  # 0-1
    time_horizon: str  # immediate, short_term, medium_term, long_term
    affected_files: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    mitigation_plan: list[str] = field(default_factory=list)
    impact: str = ""  # low, medium, high, critical
    created_at: str = ""


@dataclass
class PredictionReport:
    repo_id: str
    repo_name: str
    timestamp: str
    predictions: list[Prediction] = field(default_factory=list)
    risk_score: float = 0.0
    high_risk_count: int = 0
    medium_risk_count: int = 0
    category_breakdown: dict[str, int] = field(default_factory=dict)
    overall_instability: float = 0.0


class PredictiveEngineering:
    """Analyzes repository patterns to predict future engineering risks and failures."""

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)

    def analyze(self) -> PredictionReport:
        report = PredictionReport(
            repo_id=str(hash(str(self.repo_path))),
            repo_name=self.repo_path.name,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        self._predict_build_failures(report)
        self._predict_merge_conflicts(report)
        self._predict_deployment_failures(report)
        self._predict_performance_regressions(report)
        self._predict_security_risks(report)
        self._predict_repo_instability(report)
        self._predict_tech_debt_growth(report)
        self._predict_dependency_failures(report)

        report.high_risk_count = sum(1 for p in report.predictions if p.probability > 0.7)
        report.medium_risk_count = sum(1 for p in report.predictions if 0.4 <= p.probability <= 0.7)
        cat_counts = defaultdict(int)
        for p in report.predictions:
            cat_counts[p.category] += 1
        report.category_breakdown = dict(cat_counts)
        report.risk_score = min(100, sum(p.probability * 100 for p in report.predictions) / max(len(report.predictions), 1))
        report.overall_instability = report.risk_score / 100

        return report

    def _predict_build_failures(self, report: PredictionReport):
        evidence = []
        probability = 0.1

        py_files = list(self.repo_path.rglob("*.py"))
        syntax_errors = 0
        for f in py_files:
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                compile(content, f.name, "exec")
            except SyntaxError:
                syntax_errors += 1
                evidence.append(f"Syntax error in {f.relative_to(self.repo_path)}")

        if syntax_errors > 0:
            probability += 0.3 * min(1, syntax_errors / 5)

        large_prs = 0
        for f in py_files:
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                if len(content) > 10000:
                    large_prs += 1
            except Exception:
                pass
        if large_prs > 3:
            probability += 0.15
            evidence.append(f"{large_prs} files exceed 10KB — high change collision risk")

        if any(f.suffix == ".py" and "test" in f.name for f in py_files):
            test_files = [f for f in py_files if "test" in f.name]
            if len(test_files) < len(py_files) * 0.05:
                evidence.append("Low test coverage increases build regression risk")
                probability += 0.1

        if probability > 0.2:
            report.predictions.append(Prediction(
                id=self._pid("build_failure"),
                category="build_failure",
                description="Likelihood of build failures in the next commit cycle",
                probability=round(min(probability, 0.95), 2),
                confidence=round(0.6 + min(0.3, syntax_errors * 0.1), 2),
                time_horizon="immediate",
                evidence=evidence[:5],
                mitigation_plan=[
                    "Run full test suite before committing",
                    "Set up CI pipeline for early detection",
                    "Review large files for merge conflicts",
                    "Enable pre-commit hooks",
                ],
                impact="high" if probability > 0.5 else "medium",
            ))

    def _predict_merge_conflicts(self, report: PredictionReport):
        evidence = []
        probability = 0.15

        large_files = []
        for f in self.repo_path.rglob("*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                lines = content.count("\n") + 1
                if lines > 500:
                    large_files.append(f.relative_to(self.repo_path))
            except Exception:
                pass

        if large_files:
            probability += min(0.3, len(large_files) * 0.05)
            evidence.append(f"{len(large_files)} large files (>500 lines) — high conflict probability")

        config_files = ["requirements.txt", "package.json", "pyproject.toml", "poetry.lock", "yarn.lock"]
        for cf in config_files:
            if (self.repo_path / cf).exists():
                evidence.append(f"Shared config file {cf} — frequent merge conflict source")
                probability += 0.1
                break

        try:
            git_dir = self.repo_path / ".git"
            if git_dir.exists():
                import subprocess
                result = subprocess.run(
                    ["git", "log", "--oneline", "--all", "--since=7.days"],
                    cwd=self.repo_path, capture_output=True, text=True, timeout=5
                )
                commits_last_week = len(result.stdout.splitlines())
                if commits_last_week > 20:
                    probability += 0.15
                    evidence.append(f"High development velocity: {commits_last_week} commits in 7 days")
        except Exception:
            pass

        if probability > 0.2:
            report.predictions.append(Prediction(
                id=self._pid("merge_conflict"),
                category="merge_conflict",
                description="Likelihood of merge conflicts in active branches",
                probability=round(min(probability, 0.9), 2),
                confidence=round(0.5 + min(0.3, len(large_files) * 0.05), 2),
                time_horizon="short_term",
                evidence=evidence[:5],
                affected_files=[str(f) for f in large_files[:10]],
                mitigation_plan=[
                    "Split large files into smaller modules",
                    "Communicate before modifying shared files",
                    "Rebase frequently to reduce conflict surface",
                    "Use merge conflict detection tools",
                ],
                impact="medium",
            ))

    def _predict_deployment_failures(self, report: PredictionReport):
        evidence = []
        probability = 0.1

        deploy_configs = [
            "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
            ".github/workflows/deploy.yml", ".github/workflows/deploy.yaml",
            "k8s/deployment.yml", "helm/Chart.yaml",
        ]
        has_deployment = any((self.repo_path / d).exists() for d in deploy_configs)
        if not has_deployment:
            probability += 0.3
            evidence.append("No deployment configuration found")

        reqs = self.repo_path / "requirements.txt"
        if reqs.exists():
            reqs_content = reqs.read_text()
            pinned = re.findall(r"==(\d+\.\d+\.\d+)", reqs_content)
            unpinned = len(re.findall(r">=", reqs_content))
            if unpinned > len(pinned):
                probability += 0.15
                evidence.append("Unpinned dependencies may cause deployment failures")

        env_example = self.repo_path / ".env.example"
        if not env_example.exists():
            probability += 0.1
            evidence.append("Missing .env.example — deployment config may be incomplete")

        if probability > 0.2:
            report.predictions.append(Prediction(
                id=self._pid("deployment_failure"),
                category="deployment_failure",
                description="Likelihood of deployment failures in the next release",
                probability=round(min(probability, 0.85), 2),
                confidence=round(0.5 + has_deployment * 0.2, 2),
                time_horizon="short_term" if has_deployment else "medium_term",
                evidence=evidence[:5],
                mitigation_plan=[
                    "Add/verify Dockerfile and docker-compose configuration",
                    "Pin all dependency versions",
                    "Create .env.example with all required variables",
                    "Set up CI/CD pipeline with staging environment",
                    "Add health check endpoint",
                ],
                impact="high",
            ))

    def _predict_performance_regressions(self, report: PredictionReport):
        evidence = []
        probability = 0.1

        large_data_files = list(self.repo_path.rglob("*.pkl")) + list(self.repo_path.rglob("*.h5")) + \
                           list(self.repo_path.rglob("*.npy")) + list(self.repo_path.rglob("*.parquet"))
        if large_data_files:
            probability += 0.15
            evidence.append(f"{len(large_data_files)} large data files — memory risk")

        nested_loops = 0
        for f in self.repo_path.rglob("*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                if "for " in content and "for " in content[content.find("for ") + 4:]:
                    nested_loops += 1
            except Exception:
                pass
        if nested_loops > 5:
            probability += 0.1
            evidence.append(f"{nested_loops} files with probable nested loops")

        if probability > 0.15:
            report.predictions.append(Prediction(
                id=self._pid("performance_regression"),
                category="performance_regression",
                description="Likelihood of performance regressions in recent changes",
                probability=round(min(probability, 0.7), 2),
                confidence=round(0.4, 2),
                time_horizon="medium_term",
                evidence=evidence[:5],
                mitigation_plan=[
                    "Add performance benchmarks to CI pipeline",
                    "Review nested loops and replace with vectorized operations",
                    "Profile memory usage of data processing pipeline",
                    "Set up performance regression alerts",
                ],
                impact="medium",
            ))

    def _predict_security_risks(self, report: PredictionReport):
        evidence = []
        probability = 0.15

        risk_patterns = {
            r"api[_-]?key|apikey|api[_-]?secret": "Possible hardcoded API keys",
            r"password\s*[:=]\s*[\"']": "Possible hardcoded passwords",
            r"-----BEGIN.*PRIVATE KEY-----": "Exposed private key detected",
            r"\beval\s*\(": "eval() usage — code injection risk",
            r"\bexec\s*\(": "exec() usage — code injection risk",
            r"pickle\.loads?\(": "Unsafe deserialization",
            r"os\.system\(": "Shell injection risk",
            r"subprocess\.call\(.*shell=True": "Shell injection risk",
            r"SELECT\s+.*FROM\s+\w+\s+WHERE\s+.*=.*\+": "SQL injection risk",
        }

        for f in self.repo_path.rglob("*"):
            if f.suffix not in (".py", ".js", ".ts", ".go", ".rs", ".java", ".rb", ".php"):
                continue
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for pattern, desc in risk_patterns.items():
                if re.search(pattern, content, re.IGNORECASE):
                    evidence.append(f"{desc} in {f.relative_to(self.repo_path)}")
                    probability += 0.08
                    break

        probability = min(probability, 0.95)
        if probability >= 0.3:
            report.predictions.append(Prediction(
                id=self._pid("security_risk"),
                category="security_risk",
                description="Likelihood of security vulnerabilities in the codebase",
                probability=round(probability, 2),
                confidence=round(0.7, 2),
                time_horizon="immediate",
                evidence=evidence[:8],
                mitigation_plan=[
                    "Run security scanner (Bandit, Semgrep, etc.)",
                    "Remove all hardcoded secrets and use environment variables",
                    "Replace eval/exec with safe alternatives",
                    "Use parameterized queries for database operations",
                    "Set up SAST in CI pipeline",
                ],
                impact="high" if probability > 0.6 else "medium",
            ))

    def _predict_repo_instability(self, report: PredictionReport):
        evidence = []
        probability = 0.1

        try:
            git_dir = self.repo_path / ".git"
            if git_dir.exists():
                import subprocess
                result = subprocess.run(
                    ["git", "log", "--oneline", "--all", "--since=30.days"],
                    cwd=self.repo_path, capture_output=True, text=True, timeout=5
                )
                commit_count = len(result.stdout.splitlines())

                result2 = subprocess.run(
                    ["git", "branch", "--list"],
                    cwd=self.repo_path, capture_output=True, text=True, timeout=5
                )
                branch_count = len(result2.stdout.splitlines())

                if commit_count > 100:
                    evidence.append(f"High commit velocity: {commit_count} commits in 30 days")
                    probability += 0.15
                if branch_count > 5:
                    evidence.append(f"Many active branches: {branch_count}")
                    probability += 0.1
                    if branch_count > 15:
                        probability += 0.1

                result3 = subprocess.run(
                    ["git", "rev-list", "--count", "HEAD", "--since=30.days"],
                    cwd=self.repo_path, capture_output=True, text=True, timeout=5
                )
                try:
                    recent = int(result3.stdout.strip() or 0)
                    if recent == 0:
                        probability += 0.2
                        evidence.append("No recent commits to main — repository may be stale")
                except ValueError:
                    pass
        except Exception:
            probability += 0.1
            evidence.append("Cannot access git history — limited context")

        large_dirs = [d for d in self.repo_path.iterdir() if d.is_dir() and not d.name.startswith(".")]
        if len(large_dirs) > 8:
            evidence.append(f"Many top-level directories: {len(large_dirs)} — possible structural drift")
            probability += 0.1

        if probability > 0.2:
            report.predictions.append(Prediction(
                id=self._pid("repo_instability"),
                category="repo_instability",
                description="Likelihood of overall repository instability in the near term",
                probability=round(min(probability, 0.8), 2),
                confidence=round(0.5, 2),
                time_horizon="medium_term",
                evidence=evidence[:5],
                mitigation_plan=[
                    "Establish release cadence and branch strategy",
                    "Reduce number of active branches",
                    "Consolidate directory structure",
                    "Add repository health monitoring",
                ],
                impact="medium",
            ))

    def _predict_tech_debt_growth(self, report: PredictionReport):
        evidence = []
        probability = 0.1

        todo_count = 0
        fixme_count = 0
        for f in self.repo_path.rglob("*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                todo_count += len(re.findall(r"#\s*TODO", content))
                fixme_count += len(re.findall(r"#\s*FIXME", content))
            except Exception:
                pass

        if todo_count > 20:
            evidence.append(f"{todo_count} TODO comments — accumulating debt items")
            probability += 0.15
        if fixme_count > 5:
            evidence.append(f"{fixme_count} FIXME comments — known issues not addressed")
            probability += 0.15

        large_files = list(self.repo_path.rglob("*.py"))
        over_1k = 0
        for f in large_files:
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                if content.count("\n") > 1000:
                    over_1k += 1
            except Exception:
                pass
        if over_1k > 2:
            evidence.append(f"{over_1k} files over 1000 lines — growing faster than refactoring")
            probability += 0.1

        try:
            git_dir = self.repo_path / ".git"
            if git_dir.exists():
                import subprocess
                result = subprocess.run(
                    ["git", "log", "--oneline", "--since=90.days", "--diff-filter=D"],
                    cwd=self.repo_path, capture_output=True, text=True, timeout=5
                )
                deletions = len(result.stdout.splitlines())
                result2 = subprocess.run(
                    ["git", "log", "--oneline", "--since=90.days", "--diff-filter=A"],
                    cwd=self.repo_path, capture_output=True, text=True, timeout=5
                )
                additions = len(result2.stdout.splitlines())
                if deletions < additions * 0.2:
                    evidence.append("Low code deletion rate compared to additions — debt may be accumulating")
                    probability += 0.1
        except Exception:
            pass

        if probability > 0.2:
            report.predictions.append(Prediction(
                id=self._pid("tech_debt_growth"),
                category="tech_debt_growth",
                description="Likelihood of technical debt growing faster than resolution",
                probability=round(min(probability, 0.85), 2),
                confidence=round(0.6, 2),
                time_horizon="medium_term",
                evidence=evidence[:5],
                mitigation_plan=[
                    "Allocate 20% of sprint capacity to debt reduction",
                    "Set up automated TODO/FIXME tracking",
                    "Refactor large files into smaller modules",
                    "Track debt ratio over time in health dashboard",
                    "Establish code review checklist for debt prevention",
                ],
                impact="medium",
            ))

    def _predict_dependency_failures(self, report: PredictionReport):
        evidence = []
        probability = 0.1

        requirement_files = ["requirements.txt", "pyproject.toml", "package.json"]
        for rf in requirement_files:
            f = self.repo_path / rf
            if f.exists():
                try:
                    content = f.read_text()
                except Exception:
                    continue
                if f.name == "requirements.txt":
                    unpinned = len(re.findall(r">=", content))
                    pinned = len(re.findall(r"==", content))
                    if unpinned > pinned:
                        probability += 0.2
                        evidence.append("More unpinned than pinned dependencies in requirements.txt")
                elif f.name == "package.json":
                    try:
                        data = json.loads(content)
                        total_deps = len(data.get("dependencies", {})) + len(data.get("devDependencies", {}))
                        if total_deps > 50:
                            probability += 0.1
                            evidence.append(f"Large dependency tree: {total_deps} packages")
                    except (json.JSONDecodeError, AttributeError):
                        pass

        if (self.repo_path / "requirements.txt").exists():
            reqs_content = (self.repo_path / "requirements.txt").read_text()
            stale_packages = []
            known_packages = {
                "requests": "2.32.0", "flask": "3.1.0", "django": "5.1.0",
                "fastapi": "0.115.0", "numpy": "2.1.0", "pandas": "2.2.2",
            }
            for line in reqs_content.splitlines():
                if "==" in line:
                    pkg, ver = line.split("==", 1)
                    pkg = pkg.strip().lower()
                    ver = ver.strip()
                    if pkg in known_packages and ver != known_packages[pkg]:
                        stale_packages.append(pkg)
            if stale_packages:
                probability += 0.1
                evidence.append(f"Outdated packages: {', '.join(stale_packages[:5])}")

        if probability > 0.2:
            report.predictions.append(Prediction(
                id=self._pid("dependency_failure"),
                category="dependency_failure",
                description="Likelihood of dependency-related failures in next release cycle",
                probability=round(min(probability, 0.8), 2),
                confidence=round(0.5 + stale_packages.count(True) * 0.05 if 'stale_packages' in dir() else 0.0, 2),
                time_horizon="short_term",
                evidence=evidence[:5],
                mitigation_plan=[
                    "Pin all dependency versions",
                    "Run dependency vulnerability scan",
                    "Set up Dependabot or Renovate for automated updates",
                    "Reduce dependency count where possible",
                    "Use lockfiles (poetry.lock, yarn.lock, package-lock.json)",
                ],
                impact="high",
            ))

    def _pid(self, category: str) -> str:
        seed = f"{category}:{datetime.now(timezone.utc).isoformat()}"
        return hashlib.sha256(seed.encode()).hexdigest()[:16]
