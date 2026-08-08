"""Continuous Learning — versioned learning system that improves over time by learning repo structure, preferences, patterns, and conventions."""

import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from enum import Enum


class LearningDomain(Enum):
    REPO_STRUCTURE = "repo_structure"
    DEVELOPER_PREFERENCES = "developer_preferences"
    REVIEW_PATTERNS = "review_patterns"
    DOCUMENTATION_STYLE = "documentation_style"
    ARCHITECTURE_STYLE = "architecture_style"
    TESTING_STYLE = "testing_style"
    CODING_STANDARDS = "coding_standards"
    ORGANIZATION_CONVENTIONS = "organization_conventions"
    NAMING_CONVENTIONS = "naming_conventions"
    IMPORT_PATTERNS = "import_patterns"
    ERROR_HANDLING = "error_handling"
    API_DESIGN = "api_design"


@dataclass
class LearnedPattern:
    id: str
    domain: LearningDomain
    pattern: str
    frequency: int = 1
    confidence: float = 0.5
    first_seen: str = ""
    last_seen: str = ""
    examples: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LearningSnapshot:
    version: int
    timestamp: str
    pattern_count: int
    domains: list[str]
    summary: str = ""


class ContinuousLearning:
    """Versioned learning system that improves understanding over time."""

    LEARNING_VERSION = 1

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)
        self.learning_dir = self.repo_path / ".novaforge" / "learning"
        self.learning_dir.mkdir(parents=True, exist_ok=True)
        self.patterns: dict[str, LearnedPattern] = {}
        self.history: list[LearningSnapshot] = []
        self._version = self._load_latest_version()
        self._load_patterns()

    def learn_from_repository(self) -> int:
        """Scan the repository and learn patterns from it. Returns number of patterns learned."""
        count = 0
        count += self._learn_repo_structure()
        count += self._learn_coding_standards()
        count += self._learn_naming_conventions()
        count += self._learn_import_patterns()
        count += self._learn_error_handling()
        count += self._learn_testing_style()
        count += self._learn_documentation_style()
        count += self._learn_api_design()

        self._version += 1
        self._save_snapshot(count)
        self._save_patterns()
        return count

    def _learn_repo_structure(self) -> int:
        count = 0
        top_dirs = [d for d in self.repo_path.iterdir() if d.is_dir() and not d.name.startswith(".")]
        dir_names = [d.name for d in top_dirs]

        common_structures = {
            "src": "src layout", "app": "app layout", "lib": "lib layout",
            "services": "microservices layout", "packages": "monorepo layout",
            "backend": "backend-frontend split", "frontend": "backend-frontend split",
            "docs": "documentation dir", "tests": "test dir", "scripts": "scripts dir",
        }

        for d in dir_names:
            if d in common_structures:
                self._record_pattern(
                    LearningDomain.REPO_STRUCTURE,
                    f"directory:{d}",
                    f"Repository uses '{d}' directory — {common_structures[d]}",
                )
                count += 1

        return count

    def _learn_coding_standards(self) -> int:
        count = 0
        for f in self.repo_path.rglob("*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            has_type_hints = bool(re.search(r'def\s+\w+\(.*:\s*\w+', content))
            has_docstrings = '"""' in content
            has_annotations = bool(re.search(r'->\s*\w+', content))

            if has_type_hints:
                self._record_pattern(LearningDomain.CODING_STANDARDS, "type_hints", "Uses type hints")
                count += 1
            if has_docstrings:
                self._record_pattern(LearningDomain.CODING_STANDARDS, "docstrings", "Uses docstrings")
                count += 1
            if has_annotations:
                self._record_pattern(LearningDomain.CODING_STANDARDS, "return_annotations", "Uses return type annotations")
                count += 1
            break  # check one file

        config_files = {
            ".flake8": "flake8", "ruff.toml": "ruff", "pyproject.toml": "pyproject",
            ".pre-commit-config.yaml": "pre-commit", ".editorconfig": "editorconfig",
            ".pylintrc": "pylint", "mypy.ini": "mypy", ".isort.cfg": "isort",
        }
        for cf, tool in config_files.items():
            if (self.repo_path / cf).exists():
                self._record_pattern(LearningDomain.CODING_STANDARDS, f"tool:{tool}", f"Uses {tool}")
                count += 1

        return count

    def _learn_naming_conventions(self) -> int:
        count = 0
        for f in self.repo_path.rglob("*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            snake_case = len(re.findall(r'def\s+[a-z][a-z0-9_]*(?:\()', content))
            camel_case = len(re.findall(r'def\s+[a-z][a-zA-Z0-9]*(?:\()', content))

            if snake_case > camel_case:
                self._record_pattern(LearningDomain.NAMING_CONVENTIONS, "function_naming:snake_case",
                                     f"Functions use snake_case ({snake_case} vs {camel_case})")
                count += 1
            elif camel_case > snake_case:
                self._record_pattern(LearningDomain.NAMING_CONVENTIONS, "function_naming:camelCase",
                                     f"Functions use camelCase ({camel_case} vs {snake_case})")
                count += 1

            cls_snake = len(re.findall(r'class\s+[a-z][a-z0-9_]*:', content))
            cls_pascal = len(re.findall(r'class\s+[A-Z][a-zA-Z0-9]*:', content))

            if cls_pascal > cls_snake:
                self._record_pattern(LearningDomain.NAMING_CONVENTIONS, "class_naming:PascalCase",
                                     f"Classes use PascalCase ({cls_pascal} vs {cls_snake})")
                count += 1

            break

        return count

    def _learn_import_patterns(self) -> int:
        count = 0
        import_groups = {"stdlib": 0, "third_party": 0, "local": 0}

        for f in self.repo_path.rglob("*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            for match in re.finditer(r'^(?:from\s+(\S+)\s+import|import\s+(\S+))', content, re.MULTILINE):
                imp = match.group(1) or match.group(2)
                if imp.split(".")[0] in ("os", "sys", "re", "json", "pathlib", "collections",
                                          "datetime", "typing", "abc", "enum", "hashlib",
                                          "math", "functools", "itertools", "uuid"):
                    import_groups["stdlib"] += 1
                elif imp.split(".")[0] in ("flask", "fastapi", "django", "pytest", "numpy",
                                            "pandas", "sqlalchemy", "httpx", "requests",
                                            "pydantic", "celery", "redis"):
                    import_groups["third_party"] += 1
                else:
                    import_groups["local"] += 1

        if sum(import_groups.values()) > 0:
            self._record_pattern(LearningDomain.IMPORT_PATTERNS, "import_groups", str(import_groups))
            count += 1

        return count

    def _learn_error_handling(self) -> int:
        count = 0
        try_count = 0
        specific_except = 0
        bare_except = 0

        for f in self.repo_path.rglob("*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            try_count += len(re.findall(r'\btry\b', content))
            specific_except += len(re.findall(r'except\s+\w+', content))
            bare_except += len(re.findall(r'except\s*:', content))

        if try_count > 0:
            specificity = specific_except / max(try_count, 1)
            self._record_pattern(LearningDomain.ERROR_HANDLING, "exception_specificity",
                                 f"Exception specificity ratio: {specificity:.2f}")
            count += 1

            if bare_except > specific_except:
                self._record_pattern(LearningDomain.ERROR_HANDLING, "bare_except_usage",
                                     "Tends to use bare except clauses")
                count += 1

        return count

    def _learn_testing_style(self) -> int:
        count = 0
        for f in self.repo_path.rglob("*test*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            has_pytest = "pytest" in content or "def test_" in content
            has_unittest = "unittest" in content or "TestCase" in content
            has_fixtures = "def fixture" in content or "@pytest.fixture" in content
            has_parametrize = "@pytest.mark.parametrize" in content or "parametrize" in content
            has_mock = "mock" in content or "patch" in content

            if has_pytest:
                self._record_pattern(LearningDomain.TESTING_STYLE, "framework:pytest", "Uses pytest")
                count += 1
            if has_unittest:
                self._record_pattern(LearningDomain.TESTING_STYLE, "framework:unittest", "Uses unittest")
                count += 1
            if has_fixtures:
                self._record_pattern(LearningDomain.TESTING_STYLE, "fixtures", "Uses test fixtures")
                count += 1
            if has_parametrize:
                self._record_pattern(LearningDomain.TESTING_STYLE, "parametrize", "Uses parametrized tests")
                count += 1
            if has_mock:
                self._record_pattern(LearningDomain.TESTING_STYLE, "mocking", "Uses mocking")
                count += 1
            break

        return count

    def _learn_documentation_style(self) -> int:
        count = 0

        readme = self.repo_path / "README.md"
        if readme.exists():
            content = readme.read_text(encoding="utf-8", errors="ignore")
            sections = re.findall(r'^##\s+(.+)', content, re.MULTILINE)
            if sections:
                self._record_pattern(LearningDomain.DOCUMENTATION_STYLE, "readme_sections",
                                     f"README sections: {', '.join(sections[:5])}")
                count += 1

        docstring_style = ""
        for f in self.repo_path.rglob("*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                if ':param' in content:
                    docstring_style = "Sphinx/reST"
                elif 'Args:' in content:
                    docstring_style = "Google"
                elif 'Parameters' in content:
                    docstring_style = "NumPy"
                elif '"""' in content:
                    docstring_style = "plain"
            except Exception:
                continue
            if docstring_style:
                self._record_pattern(LearningDomain.DOCUMENTATION_STYLE, f"docstring:{docstring_style}",
                                     f"Uses {docstring_style} docstring style")
                count += 1
                break

        return count

    def _learn_api_design(self) -> int:
        count = 0
        for f in self.repo_path.rglob("*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            routes = re.findall(r'@\w+\.(?:get|post|put|delete|patch)\s*\([\'"](\S+)[\'"]', content)
            if routes:
                self._record_pattern(LearningDomain.API_DESIGN, "api_routes",
                                     f"API routes follow pattern: {routes[0][:30]}...")
                count += 1

            has_pydantic = "BaseModel" in content or "pydantic" in content
            if has_pydantic:
                self._record_pattern(LearningDomain.API_DESIGN, "validation:pydantic", "Uses Pydantic for validation")
                count += 1

            break

        return count

    def _record_pattern(self, domain: LearningDomain, pattern_id: str, example: str):
        pid = hashlib.sha256(f"{domain.value}:{pattern_id}".encode()).hexdigest()[:16]
        now = datetime.now(timezone.utc).isoformat()

        if pid in self.patterns:
            self.patterns[pid].frequency += 1
            self.patterns[pid].confidence = min(1.0, self.patterns[pid].confidence + 0.05)
            self.patterns[pid].last_seen = now
            if len(self.patterns[pid].examples) < 3:
                self.patterns[pid].examples.append(example)
        else:
            self.patterns[pid] = LearnedPattern(
                id=pid,
                domain=domain,
                pattern=pattern_id,
                frequency=1,
                confidence=0.3,
                first_seen=now,
                last_seen=now,
                examples=[example],
            )

    def get_patterns(self, domain: Optional[LearningDomain] = None,
                     min_confidence: float = 0.0) -> list[LearnedPattern]:
        results = list(self.patterns.values())
        if domain:
            results = [p for p in results if p.domain == domain]
        if min_confidence > 0:
            results = [p for p in results if p.confidence >= min_confidence]
        return sorted(results, key=lambda p: -p.confidence)

    def get_domain_summary(self) -> dict[str, dict]:
        summary = defaultdict(lambda: {"count": 0, "avg_confidence": 0.0, "patterns": []})
        for p in self.patterns.values():
            domain = p.domain.value
            summary[domain]["count"] += 1
            summary[domain]["avg_confidence"] += p.confidence
            summary[domain]["patterns"].append(p.pattern)

        for v in summary.values():
            v["avg_confidence"] = round(v["avg_confidence"] / max(v["count"], 1), 3)

        return dict(summary)

    def get_learning_statistics(self) -> dict[str, Any]:
        return {
            "version": self._version,
            "total_patterns": len(self.patterns),
            "domains": len(set(p.domain.value for p in self.patterns.values())),
            "avg_confidence": round(
                sum(p.confidence for p in self.patterns.values()) / max(len(self.patterns), 1), 3
            ),
            "highest_confidence": max((p.confidence for p in self.patterns.values()), default=0),
            "history_count": len(self.history),
            "learning_dir": str(self.learning_dir),
        }

    def _load_latest_version(self) -> int:
        version_file = self.learning_dir / "version.txt"
        if version_file.exists():
            try:
                return int(version_file.read_text().strip())
            except (ValueError, OSError):
                pass
        return 0

    def _load_patterns(self):
        pattern_file = self.learning_dir / f"patterns_v{self._version}.json"
        if pattern_file.exists():
            try:
                data = json.loads(pattern_file.read_text())
                for p in data.get("patterns", []):
                    p_obj = LearnedPattern(**p)
                    p_obj.domain = LearningDomain(p_obj.domain) if isinstance(p_obj.domain, str) else p_obj.domain
                    self.patterns[p_obj.id] = p_obj
            except Exception:
                pass

        history_file = self.learning_dir / "history.json"
        if history_file.exists():
            try:
                data = json.loads(history_file.read_text())
                self.history = [LearningSnapshot(**h) for h in data.get("snapshots", [])]
            except Exception:
                pass

    def _save_patterns(self):
        pattern_file = self.learning_dir / f"patterns_v{self._version}.json"
        data = {
            "version": self._version,
            "patterns": [
                {**p.__dict__, "domain": p.domain.value if isinstance(p.domain, LearningDomain) else p.domain}
                for p in self.patterns.values()
            ],
        }
        pattern_file.write_text(json.dumps(data, indent=2, default=str))

        version_file = self.learning_dir / "version.txt"
        version_file.write_text(str(self._version))

    def _save_snapshot(self, pattern_count: int):
        snapshot = LearningSnapshot(
            version=self._version,
            timestamp=datetime.now(timezone.utc).isoformat(),
            pattern_count=pattern_count,
            domains=list(set(p.domain.value for p in self.patterns.values())),
            summary=f"Learned {pattern_count} new patterns (total: {len(self.patterns)})",
        )
        self.history.append(snapshot)
        if len(self.history) > 100:
            self.history = self.history[-100:]

        history_file = self.learning_dir / "history.json"
        history_file.write_text(json.dumps({
            "snapshots": [h.__dict__ for h in self.history],
        }, indent=2, default=str))
