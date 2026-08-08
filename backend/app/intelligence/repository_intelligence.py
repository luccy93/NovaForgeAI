"""Repository Intelligence — continuous analysis, health scores, technical debt, security & dependency risks."""

import ast
import json
import os
import re
import subprocess
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, field

import httpx


@dataclass
class RepoHealthScore:
    overall: float = 0.0
    code_quality: float = 0.0
    security: float = 0.0
    dependencies: float = 0.0
    documentation: float = 0.0
    activity: float = 0.0
    coverage: Optional[float] = None
    issues: int = 0
    prs_open: int = 0
    branches: int = 0


@dataclass
class TechDebtItem:
    file: str
    line: int
    severity: str  # low, medium, high, critical
    category: str  # complexity, duplication, dead_code, anti_pattern, style
    description: str
    suggestion: str


@dataclass
class SecurityRisk:
    file: str
    line: int
    severity: str
    cwe: Optional[str] = None
    description: str = ""
    recommendation: str = ""


@dataclass
class DependencyRisk:
    package: str
    current_version: str
    latest_version: str
    is_outdated: bool = False
    has_vulnerability: bool = False
    vulnerability_count: int = 0
    breaking_changes: bool = False
    license: str = ""


@dataclass
class DuplicateBlock:
    files: list[str]
    lines: list[tuple[int, int]]
    similarity: float
    content_hash: str


@dataclass
class RepositoryAnalysis:
    repo_id: str
    repo_name: str
    language_stats: dict[str, int] = field(default_factory=dict)
    file_count: int = 0
    total_lines: int = 0
    health: RepoHealthScore = field(default_factory=RepoHealthScore)
    tech_debt: list[TechDebtItem] = field(default_factory=list)
    security_risks: list[SecurityRisk] = field(default_factory=list)
    dependency_risks: list[DependencyRisk] = field(default_factory=list)
    duplicates: list[DuplicateBlock] = field(default_factory=list)
    dead_code: list[dict] = field(default_factory=list)
    architecture: dict = field(default_factory=dict)
    analyzed_at: str = ""


class RepositoryIntelligence:
    """Continuously analyzes repositories for health, debt, security, dependencies, and architecture."""

    SECURITY_PATTERNS = {
        "api_key": (r'(?:api[_-]?key|apikey|api[_-]?secret)\s*[:=]\s*["\']?[\w-]{16,}', "high"),
        "password": (r'(?:password|passwd|pwd)\s*[:=]\s*["\'][^"\']+["\']', "high"),
        "aws_key": (r'AKIA[0-9A-Z]{16}', "high"),
        "private_key": (r'-----BEGIN (?:RSA |EC )?PRIVATE KEY-----', "critical"),
        "token": (r'(?:token|bearer|auth)\s*[:=]\s*["\']?[\w-]{20,}', "medium"),
        "connection_string": (r'(?:mongodb|postgresql|mysql|redis)://[^\s]+', "medium"),
        "jwt": (r'eyJ[A-Za-z0-9-_]+\.eyJ[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+', "high"),
        "npm_token": (r'npm_[A-Za-z0-9]{36}', "high"),
        "github_token": (r'gh[pousr]_[A-Za-z0-9]{36}', "high"),
    }

    DEAD_CODE_PATTERNS = {
        ".py": [
            (r'^def (\w+)\(.*\):.*\n(?:^    .*\n)*^\S', "unused_function"),
            (r'^class (\w+).*:.*\n(?:^    .*\n)*^\S', "unused_class"),
        ],
        ".js": [
            (r'function (\w+)\s*\(', "unused_function"),
            (r'const (\w+)\s*=\s*\(.*\)\s*=>', "unused_function"),
        ],
        ".ts": [
            (r'function (\w+)\s*\(', "unused_function"),
            (r'const (\w+)\s*:\s*\w+\s*=\s*\(', "unused_function"),
        ],
    }

    ANTI_PATTERNS = {
        ".py": [
            (r'try\s*:.*\n.*except\s*:\s*pass', "empty_except", "low"),
            (r'except\s+Exception\s*:', "bare_except", "medium"),
            (r'\.\s*strip\(\).*strip\(\)', "double_strip", "low"),
            (r'while\s+True\s*:', "while_true", "low"),
            (r'import\s+\*', "wildcard_import", "medium"),
            (r'os\.system\(', "shell_injection", "high"),
            (r'eval\(', "eval_usage", "critical"),
            (r'exec\(', "exec_usage", "critical"),
            (r'__import__\(', "dynamic_import", "medium"),
            (r'pickle\.loads?\(', "unsafe_deserialization", "high"),
        ],
    }

    KNOWN_VULNERABLE_PACKAGES = {
        "lodash": {"min": "4.17.21", "cves": ["CVE-2024-23346"]},
        "axios": {"min": "1.7.4", "cves": ["CVE-2024-39338"]},
        "requests": {"min": "2.32.0", "cves": ["CVE-2024-35195"]},
        "urllib3": {"min": "2.2.2", "cves": ["CVE-2024-37891"]},
        "cryptography": {"min": "42.0.4", "cves": ["CVE-2024-26130"]},
        "jinja2": {"min": "3.1.4", "cves": ["CVE-2024-34064"]},
        "werkzeug": {"min": "3.0.3", "cves": ["CVE-2024-34069"]},
        "flask": {"min": "3.0.3", "cves": ["CVE-2024-34069"]},
        "fastapi": {"min": "0.111.0", "cves": []},
        "starlette": {"min": "0.37.2", "cves": ["CVE-2024-47874"]},
        "httpx": {"min": "0.27.2", "cves": ["CVE-2024-3651"]},
        "cryptography": {"min": "42.0.4", "cves": ["CVE-2024-26130"]},
    }

    @staticmethod
    def detect_language(file_path: str) -> Optional[str]:
        ext = Path(file_path).suffix.lower()
        lang_map = {
            ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
            ".jsx": "React", ".tsx": "React TypeScript", ".go": "Go",
            ".rs": "Rust", ".java": "Java", ".kt": "Kotlin",
            ".rb": "Ruby", ".php": "PHP", ".c": "C", ".cpp": "C++",
            ".h": "C/C++ Header", ".cs": "C#", ".swift": "Swift",
            ".scala": "Scala", ".r": "R", ".m": "Objective-C",
            ".sql": "SQL", ".sh": "Shell", ".yaml": "YAML",
            ".yml": "YAML", ".json": "JSON", ".xml": "XML",
            ".md": "Markdown", ".rst": "reStructuredText",
            ".html": "HTML", ".css": "CSS", ".scss": "SCSS",
            ".less": "Less", ".dockerfile": "Dockerfile",
            ".tf": "Terraform", ".vue": "Vue",
        }
        return lang_map.get(ext)

    @staticmethod
    def analyze_directory(repo_path: str) -> RepositoryAnalysis:
        repo_path = Path(repo_path)
        analysis = RepositoryAnalysis(
            repo_id=str(hash(str(repo_path))),
            repo_name=repo_path.name,
            analyzed_at=datetime.now(timezone.utc).isoformat(),
        )

        lang_lines: Counter = Counter()
        lang_files: Counter = Counter()
        total_lines = 0
        file_count = 0

        for file_path in repo_path.rglob("*"):
            if file_path.is_file() and not any(
                part.startswith(".") or part == "node_modules" or part == "__pycache__"
                or part == ".git" or part == "venv" or part == ".venv"
                for part in file_path.parts
            ):
                lang = RepositoryIntelligence.detect_language(str(file_path))
                if lang:
                    try:
                        content = file_path.read_text(encoding="utf-8", errors="ignore")
                        lines = content.count("\n") + 1
                        total_lines += lines
                        file_count += 1
                        lang_lines[lang] += lines
                        lang_files[lang] += 1
                    except Exception:
                        pass

        analysis.language_stats = dict(lang_files)
        analysis.file_count = file_count
        analysis.total_lines = total_lines

        security_risks, tech_debt, duplicates, dead_code = (
            RepositoryIntelligence._scan_for_issues(repo_path)
        )
        analysis.security_risks = security_risks
        analysis.tech_debt = tech_debt
        analysis.duplicates = duplicates
        analysis.dead_code = dead_code

        dep_risks = RepositoryIntelligence._analyze_dependencies(repo_path)
        analysis.dependency_risks = dep_risks

        arch = RepositoryIntelligence._detect_architecture(repo_path, lang_files)
        analysis.architecture = arch

        docs_ratio = lang_files.get("Markdown", 0) / max(file_count, 1)
        test_ratio = sum(
            v for k, v in lang_files.items() if "test" in str(k).lower()
        ) / max(file_count, 1)

        analysis.health = RepoHealthScore(
            code_quality=max(0, 100 - len(tech_debt) * 2),
            security=max(0, 100 - len(security_risks) * 5),
            dependencies=max(0, 100 - len(dep_risks) * 3),
            documentation=min(100, docs_ratio * 500),
            activity=50.0,
            coverage=test_ratio * 100,
            issues=len(security_risks) + len(tech_debt),
        )
        scores = [
            analysis.health.code_quality,
            analysis.health.security,
            analysis.health.dependencies,
            analysis.health.documentation,
            analysis.health.activity,
        ]
        analysis.health.overall = sum(scores) / len(scores)

        return analysis

    @staticmethod
    def _scan_for_issues(repo_path: Path) -> tuple[list, list, list, list]:
        security_risks: list[SecurityRisk] = []
        tech_debt: list[TechDebtItem] = []
        duplicates: list[DuplicateBlock] = []
        dead_code: list[dict] = []
        content_hashes: dict[str, list[tuple[str, int, int]]] = {}

        for file_path in repo_path.rglob("*"):
            if not file_path.is_file() or any(
                p.startswith(".") or p in ("node_modules", "__pycache__", ".git", "venv", ".venv")
                for p in file_path.parts
            ):
                continue
            ext = file_path.suffix.lower()
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            rel_path = str(file_path.relative_to(repo_path))

            for name, (pattern, severity) in RepositoryIntelligence.SECURITY_PATTERNS.items():
                for match in re.finditer(pattern, content, re.IGNORECASE):
                    line_num = content[: match.start()].count("\n") + 1
                    security_risks.append(SecurityRisk(
                        file=rel_path,
                        line=line_num,
                        severity=severity,
                        cwe=f"CWE-{name}",
                        description=f"Potential {name} exposure",
                        recommendation=f"Remove or rotate the exposed {name}. Use environment variables or a vault.",
                    ))

            for pattern, category, severity in RepositoryIntelligence.ANTI_PATTERNS.get(ext, []):
                for match in re.finditer(pattern, content, re.MULTILINE):
                    line_num = content[: match.start()].count("\n") + 1
                    tech_debt.append(TechDebtItem(
                        file=rel_path,
                        line=line_num,
                        severity=severity,
                        category="anti_pattern",
                        description=f"Anti-pattern: {category}",
                        suggestion=RepositoryIntelligence._suggestion_for(category),
                    ))

            for line in content.split("\n"):
                stripped = line.strip()
                if stripped and not stripped.startswith(("#", "//", "/*", "*", "<!--")):
                    block_hash = hashlib.md5(stripped.encode()).hexdigest()
                    line_num = content[: content.find(stripped)].count("\n") + 1
                    if block_hash not in content_hashes:
                        content_hashes[block_hash] = []
                    content_hashes[block_hash].append((rel_path, line_num, len(stripped)))

        for h, occurrences in content_hashes.items():
            if len(occurrences) >= 2 and any(o[2] > 20 for o in occurrences):
                files = list(set(o[0] for o in occurrences))
                lines = [(o[1], o[1]) for o in occurrences]
                duplicates.append(DuplicateBlock(
                    files=files,
                    lines=lines,
                    similarity=100.0,
                    content_hash=h,
                ))

        return security_risks, tech_debt, duplicates, dead_code

    @staticmethod
    def _suggestion_for(category: str) -> str:
        suggestions = {
            "empty_except": "Add exception handling logic or use a more specific exception type",
            "bare_except": "Catch specific exceptions instead of bare Exception",
            "double_strip": "Chain calls are redundant; use a single strip()",
            "while_true": "Consider adding a timeout or breaking condition",
            "wildcard_import": "Import specific names instead of using *",
            "shell_injection": "Use subprocess with argument list instead of shell=True",
            "eval_usage": "Avoid eval(); use ast.literal_eval or a proper parser",
            "exec_usage": "Avoid exec(); use a function or method instead",
            "dynamic_import": "Use static imports for better tooling support",
            "unsafe_deserialization": "Use json or a safer serialization format",
        }
        return suggestions.get(category, "Review and refactor this code")

    @staticmethod
    def _analyze_dependencies(repo_path: Path) -> list[DependencyRisk]:
        risks: list[DependencyRisk] = []

        req_file = repo_path / "requirements.txt"
        if req_file.exists():
            try:
                for line in req_file.read_text().splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "==" in line:
                        pkg, ver = line.split("==", 1)
                        pkg = pkg.strip().lower()
                        ver = ver.strip()
                        if pkg in RepositoryIntelligence.KNOWN_VULNERABLE_PACKAGES:
                            info = RepositoryIntelligence.KNOWN_VULNERABLE_PACKAGES[pkg]
                            risks.append(DependencyRisk(
                                package=pkg,
                                current_version=ver,
                                latest_version=info["min"],
                                is_outdated=ver < info["min"],
                                has_vulnerability=len(info["cves"]) > 0,
                                vulnerability_count=len(info["cves"]),
                            ))
            except Exception:
                pass

        pkg_file = repo_path / "package.json"
        if pkg_file.exists():
            try:
                pkg_data = json.loads(pkg_file.read_text())
                for deps in (pkg_data.get("dependencies", {}), pkg_data.get("devDependencies", {})):
                    for pkg, ver in deps.items():
                        pkg_lower = pkg.lower()
                        if pkg_lower in RepositoryIntelligence.KNOWN_VULNERABLE_PACKAGES:
                            info = RepositoryIntelligence.KNOWN_VULNERABLE_PACKAGES[pkg_lower]
                            current = ver.lstrip("^~>=<")
                            risks.append(DependencyRisk(
                                package=pkg,
                                current_version=current,
                                latest_version=info["min"],
                                is_outdated=current < info["min"],
                                has_vulnerability=len(info["cves"]) > 0,
                                vulnerability_count=len(info["cves"]),
                            ))
            except Exception:
                pass

        return risks

    @staticmethod
    def _detect_architecture(repo_path: Path, lang_stats: Counter) -> dict:
        arch = {
            "has_monorepo": False,
            "has_microservices": False,
            "frontend_framework": None,
            "backend_framework": None,
            "database": None,
            "ci_cd": None,
            "containerization": None,
            "modules": [],
            "layers": [],
        }

        has_docker = any(
            f.name.lower() in ("dockerfile", "docker-compose.yml", "docker-compose.yaml")
            for f in repo_path.rglob("*") if f.is_file()
        )
        arch["containerization"] = "Docker" if has_docker else None

        has_ci = any(
            (".github/workflows" in str(f) or ".gitlab-ci.yml" in str(f) or "Jenkinsfile" in str(f))
            for f in repo_path.rglob("*") if f.is_file()
        )
        arch["ci_cd"] = "GitHub Actions" if (repo_path / ".github").exists() else \
                        "GitLab CI" if (repo_path / ".gitlab-ci.yml").exists() else \
                        "Jenkins" if any(f.name == "Jenkinsfile" for f in repo_path.rglob("*")) else None

        subdirs = [d.name for d in repo_path.iterdir() if d.is_dir() and not d.name.startswith(".")]
        if len(subdirs) >= 3 and len([d for d in subdirs if d in ("services", "apps", "packages")]) >= 2:
            arch["has_monorepo"] = True

        if (repo_path / "requirements.txt").exists() or any(
            (repo_path / d / "requirements.txt").exists()
            for d in subdirs
        ):
            arch["backend_framework"] = "Python"
        if (repo_path / "package.json").exists():
            try:
                pkg = json.loads((repo_path / "package.json").read_text())
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                for key, fw in [("react", "React"), ("vue", "Vue"), ("@angular", "Angular"),
                               ("next", "Next.js"), ("nuxt", "Nuxt"), ("svelte", "Svelte")]:
                    if key in deps:
                        arch["frontend_framework"] = fw
                        break
            except Exception:
                pass

        return arch


import hashlib  # noqa: E402
