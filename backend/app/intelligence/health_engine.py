"""Repository Health Engine — comprehensive health scoring with historical trends."""

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


@dataclass
class HealthScore:
    overall: float = 0.0
    architecture: float = 0.0
    maintainability: float = 0.0
    security: float = 0.0
    performance: float = 0.0
    testing: float = 0.0
    documentation: float = 0.0
    deployment_readiness: float = 0.0
    technical_debt: float = 0.0
    ai_readiness: float = 0.0
    repository_maturity: float = 0.0


@dataclass
class HealthSnapshot:
    timestamp: str
    scores: HealthScore = field(default_factory=HealthScore)
    details: dict[str, Any] = field(default_factory=dict)


class RepositoryHealthEngine:
    """Calculates comprehensive repository health scores with historical trend tracking."""

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)
        self.history: list[HealthSnapshot] = []

    def calculate(self) -> HealthScore:
        scores = HealthScore()

        scores.architecture = self._score_architecture()
        scores.maintainability = self._score_maintainability()
        scores.security = self._score_security()
        scores.performance = self._score_performance()
        scores.testing = self._score_testing()
        scores.documentation = self._score_documentation()
        scores.deployment_readiness = self._score_deployment_readiness()
        scores.technical_debt = self._score_technical_debt()
        scores.ai_readiness = self._score_ai_readiness()
        scores.repository_maturity = self._score_repository_maturity()

        weights = {
            "architecture": 0.15, "maintainability": 0.15, "security": 0.15,
            "performance": 0.10, "testing": 0.10, "documentation": 0.10,
            "deployment_readiness": 0.10, "technical_debt": 0.05, "ai_readiness": 0.05,
            "repository_maturity": 0.05,
        }
        scores.overall = sum(
            getattr(scores, k) * v for k, v in weights.items()
        )

        self.history.append(HealthSnapshot(
            timestamp=datetime.now(timezone.utc).isoformat(),
            scores=scores,
        ))
        if len(self.history) > 500:
            self.history = self.history[-500:]

        return scores

    def _score_architecture(self) -> float:
        score = 50.0
        arch_docs = list(self.repo_path.rglob("ARCHITECTURE*")) + list(self.repo_path.rglob("architecture*"))
        if arch_docs:
            score += 10

        di_containers = ["docker-compose.yml", "docker-compose.yaml", "Dockerfile"]
        if any((self.repo_path / f).exists() for f in di_containers):
            score += 10

        ci_dirs = [".github/workflows", ".gitlab-ci.yml"]
        if any((self.repo_path / d).exists() if "." in d else any(
            f.is_file() for f in self.repo_path.rglob(d.split("/")[-1])
        ) for d in ci_dirs):
            score += 10

        if (self.repo_path / "Makefile").exists() or (self.repo_path / "Justfile").exists():
            score += 5

        readme = self.repo_path / "README.md"
        if readme.exists() and "architecture" in readme.read_text().lower():
            score += 5

        src_dirs = [d for d in self.repo_path.iterdir() if d.is_dir() and not d.name.startswith(".")]
        if len(src_dirs) > 1:
            score += 5
        if len(src_dirs) > 4:
            score += 5

        return min(100, score)

    def _score_maintainability(self) -> float:
        score = 60.0
        py_files = list(self.repo_path.rglob("*.py"))
        total_complexity = 0
        func_count = 0
        total_lines = 0
        large_files = 0

        for f in py_files:
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            lines = content.count("\n") + 1
            total_lines += lines
            if lines > 500:
                large_files += 1

            import ast
            try:
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        func_count += 1
                        complexity = 1
                        for child in ast.walk(node):
                            if isinstance(child, (ast.If, ast.While, ast.For, ast.ExceptHandler,
                                                  ast.AsyncFor)):
                                complexity += 1
                            elif isinstance(child, ast.BoolOp):
                                complexity += len(child.values) - 1
                        total_complexity += complexity
            except SyntaxError:
                pass

        if func_count > 0:
            avg_complexity = total_complexity / func_count
            if avg_complexity > 10:
                score -= 20
            elif avg_complexity > 7:
                score -= 10
            elif avg_complexity > 4:
                score -= 5

        if large_files > 0:
            score -= min(15, large_files * 3)

        if total_lines == 0:
            return 50.0

        return max(0, min(100, score))

    def _score_security(self) -> float:
        score = 70.0
        risk_patterns = {
            r"api[_-]?key\s*[:=]\s*[\"']?[\w-]{16,}": 10,
            r"password\s*[:=]\s*[\"']": 10,
            r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----": 30,
            r"eval\s*\(": 15,
            r"exec\s*\(": 15,
            r"os\.system\(": 10,
            r"pickle\.loads?\(": 10,
            r"subprocess\.call\(.*shell=True": 10,
            r"SELECT\s+.*\s+FROM\s+.*\s+WHERE\s+.*=.*" + '["\']': 5,
        }

        for f in self.repo_path.rglob("*"):
            if not f.is_file() or f.suffix not in (".py", ".js", ".ts", ".go", ".rs", ".java", ".rb", ".php"):
                continue
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for pattern, penalty in risk_patterns.items():
                if re.search(pattern, content, re.IGNORECASE):
                    score -= penalty

        if (self.repo_path / ".safety-policy.yml").exists() or (self.repo_path / ".bandit").exists():
            score += 10

        return max(0, min(100, score))

    def _score_performance(self) -> float:
        score = 60.0
        has_perf_tools = False

        perf_patterns = [
            r"async\s+def", r"asyncio", r"concurrent\.futures",
            r"@lru_cache", r"@cache", r"functools\.lru_cache",
            r"cProfile", r"profile",
            r"timeit", r"perf_counter",
        ]

        for f in self.repo_path.rglob("*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if any(re.search(p, content) for p in perf_patterns):
                has_perf_tools = True
                score += 5

        if has_perf_tools:
            score += 10

        large_objects = list(self.repo_path.rglob("*.pkl")) + list(self.repo_path.rglob("*.h5"))
        if large_objects:
            score -= min(10, len(large_objects) * 2)

        return min(100, score)

    def _score_testing(self) -> float:
        score = 40.0
        test_files = list(self.repo_path.rglob("test_*")) + list(self.repo_path.rglob("*_test*")) + \
                     list(self.repo_path.rglob("*_test.go")) + list(self.repo_path.rglob("*.spec.*"))
        test_dirs = [d for d in self.repo_path.rglob("*") if d.is_dir() and "test" in d.name.lower()]

        test_count = len(test_files)
        if test_count > 0:
            score += min(30, test_count * 3)

        if test_dirs:
            score += 10

        if (self.repo_path / "pytest.ini").exists() or (self.repo_path / "pytest.ini").exists():
            score += 5
        if (self.repo_path / "jest.config.js").exists() or (self.repo_path / "jest.config.ts").exists():
            score += 5
        if (self.repo_path / ".coveragerc").exists() or (self.repo_path / "coverage.py").exists():
            score += 5

        conftest = list(self.repo_path.rglob("conftest.py"))
        if conftest:
            score += 5

        total_files = len(list(self.repo_path.rglob("*.py"))) + len(list(self.repo_path.rglob("*.js"))) + \
                      len(list(self.repo_path.rglob("*.ts")))
        if total_files > 0 and test_count > 0:
            ratio = test_count / total_files
            if ratio > 0.3:
                score += 10
            elif ratio > 0.1:
                score += 5

        return min(100, score)

    def _score_documentation(self) -> float:
        score = 30.0

        readme = self.repo_path / "README.md"
        if readme.exists():
            content = readme.read_text(encoding="utf-8", errors="ignore")
            score += 15
            sections = ["installation", "usage", "api", "configuration", "contributing", "license"]
            found = sum(1 for s in sections if re.search(s, content, re.IGNORECASE))
            score += min(15, found * 2.5)

        doc_files = list(self.repo_path.rglob("*.md")) + list(self.repo_path.rglob("*.rst")) + \
                    list(self.repo_path.rglob("*.txt"))
        if len(doc_files) > 3:
            score += 10
        if len(doc_files) > 10:
            score += 5

        doc_dirs = ["docs", "documentation", "wiki"]
        if any((self.repo_path / d).exists() for d in doc_dirs):
            score += 10

        if (self.repo_path / "CONTRIBUTING.md").exists():
            score += 5
        if (self.repo_path / "CHANGELOG.md").exists():
            score += 5
        if (self.repo_path / "LICENSE").exists() or (self.repo_path / "LICENSE.txt").exists():
            score += 5

        source_files = list(self.repo_path.rglob("*.py")) + list(self.repo_path.rglob("*.js"))
        docstring_count = 0
        total_funcs = 0
        for f in source_files[:50]:
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                funcs = re.findall(r'def\s+\w+\s*\(', content)
                total_funcs += len(funcs)
                docstrings = re.findall(r'""".*?"""', content, re.DOTALL)
                docstring_count += len(docstrings)
            except Exception:
                pass
        if total_funcs > 0:
            doc_ratio = docstring_count / total_funcs
            score += min(10, doc_ratio * 20)

        return min(100, score)

    def _score_deployment_readiness(self) -> float:
        score = 40.0

        if (self.repo_path / "Dockerfile").exists():
            score += 15
        if (self.repo_path / "docker-compose.yml").exists() or (self.repo_path / "docker-compose.yaml").exists():
            score += 10

        if (self.repo_path / "requirements.txt").exists() or (self.repo_path / "pyproject.toml").exists():
            score += 5
        if (self.repo_path / "package.json").exists():
            score += 5

        if (self.repo_path / ".env.example").exists() or (self.repo_path / ".env.sample").exists():
            score += 5

        if (self.repo_path / ".github/workflows").exists():
            score += 10

        if (self.repo_path / "Makefile").exists() or (self.repo_path / "Justfile").exists():
            score += 5

        if (self.repo_path / "helm").exists() or (self.repo_path / "k8s").exists() or \
           (self.repo_path / "kubernetes").exists():
            score += 10
        if (self.repo_path / "terraform").exists() or (self.repo_path / "main.tf").exists():
            score += 5

        health_path = self.repo_path / "healthcheck.py" if (self.repo_path / "healthcheck.py").exists() else None
        if not health_path:
            health_path = self.repo_path / "health" if (self.repo_path / "health").exists() else None
        if health_path:
            score += 5

        return min(100, score)

    def _score_technical_debt(self) -> float:
        score = 60.0
        debt_items = 0

        for f in self.repo_path.rglob("*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            if content.count("\n") > 1000:
                debt_items += 1
                score -= 5

            todo_count = len(re.findall(r"#\s*(TODO|FIXME|HACK|XXX)", content))
            if todo_count > 5:
                debt_items += todo_count // 5
                score -= min(10, todo_count)

            if re.search(r"except\s*:\s*pass", content):
                debt_items += 1
                score -= 3
            if re.search(r"import\s+\*", content):
                debt_items += 1
                score -= 2
            if re.search(r"while\s+True", content):
                debt_items += 1
                score -= 1

        return max(0, min(100, score))

    def _score_ai_readiness(self) -> float:
        score = 50.0

        if (self.repo_path / "requirements.txt").exists():
            reqs = (self.repo_path / "requirements.txt").read_text()
            ai_packages = ["openai", "anthropic", "langchain", "transformers", "torch", "tensorflow",
                          "sklearn", "scikit-learn", "pytorch", "huggingface", "llama", "ollama"]
            found = sum(1 for pkg in ai_packages if pkg in reqs.lower())
            score += min(20, found * 3)

        has_ai_dirs = any(
            d.name.lower() in ("ai", "ml", "model", "models", "inference", "training", "llm", "rag", "embedding")
            for d in self.repo_path.iterdir() if d.is_dir()
        )
        if has_ai_dirs:
            score += 10

        has_ai_files = any(
            f.suffix == ".pt" or f.suffix == ".pth" or f.suffix == ".onnx" or "model" in f.name.lower()
            for f in self.repo_path.rglob("*") if f.is_file()
        )
        if has_ai_files:
            score += 5

        if (self.repo_path / "prompts").exists() or list(self.repo_path.rglob("*.prompt")):
            score += 5

        if (self.repo_path / "embeddings").exists() or (self.repo_path / "vectors").exists():
            score += 5

        if (self.repo_path / "Makefile").exists() and any(
            target in (self.repo_path / "Makefile").read_text().lower()
            for target in ["train", "evaluate", "predict", "infer"]
        ):
            score += 5

        return min(100, score)

    def _score_repository_maturity(self) -> float:
        score = 30.0

        git_dir = self.repo_path / ".git"
        if git_dir.exists():
            score += 10
            try:
                log_output = subprocess.check_output(
                    ["git", "log", "--oneline"], cwd=self.repo_path, stderr=subprocess.DEVNULL
                ).decode()
                commit_count = len(log_output.splitlines())
                if commit_count > 100:
                    score += 10
                elif commit_count > 50:
                    score += 5
                elif commit_count > 10:
                    score += 2
            except Exception:
                pass

        if (self.repo_path / "LICENSE").exists():
            score += 5
        if (self.repo_path / "CHANGELOG.md").exists():
            score += 5
        if (self.repo_path / "CONTRIBUTING.md").exists():
            score += 5
        if (self.repo_path / "CODE_OF_CONDUCT.md").exists():
            score += 5

        if (self.repo_path / ".github/ISSUE_TEMPLATE").exists():
            score += 5
        if (self.repo_path / ".github/PULL_REQUEST_TEMPLATE").exists() or \
           (self.repo_path / "PULL_REQUEST_TEMPLATE.md").exists():
            score += 5

        has_versioning = bool(
            (self.repo_path / "VERSION").exists() or
            (self.repo_path / "version.py").exists() or
            (self.repo_path / "version.go").exists() or
            (self.repo_path / "package.json").exists()
        )
        if has_versioning:
            score += 5

        releases = list(self.repo_path.rglob("*.tar.gz")) + list(self.repo_path.rglob("*.whl"))
        if releases:
            score += 5

        configs = [".editorconfig", ".pre-commit-config.yaml", ".flake8", "ruff.toml", ".prettierrc",
                   ".eslintrc", ".eslintrc.json", "tsconfig.json"]
        found_configs = sum(1 for c in configs if (self.repo_path / c).exists())
        score += min(10, found_configs * 2)

        return min(100, score)

    def get_trend(self, metric: str = "overall") -> list[dict]:
        result = []
        for snap in self.history[-100:]:
            value = getattr(snap.scores, metric, None)
            if value is not None:
                result.append({
                    "timestamp": snap.timestamp,
                    "value": round(value, 2),
                    "metric": metric,
                })
        return result

    def get_summary(self) -> dict[str, Any]:
        if not self.history:
            return {"error": "No health data available"}
        latest = self.history[-1].scores
        return {
            "current": {k: round(v, 2) for k, v in latest.__dict__.items()},
            "trends": {metric: self.get_trend(metric) for metric in latest.__dict__.keys()},
            "snapshot_count": len(self.history),
            "first_analysis": self.history[0].timestamp if self.history else None,
            "last_analysis": self.history[-1].timestamp if self.history else None,
        }


import subprocess  # noqa: E402
