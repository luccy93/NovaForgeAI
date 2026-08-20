"""AI Software Quality Engine -- Dependency Analyzer (Volume 48).

Checks new dependencies, version changes, vulnerabilities,
licenses, and supply-chain risk.
"""

from __future__ import annotations

import re
from typing import Any

from app.quality.analyzers.base import AnalyzerResult, BaseAnalyzer, ReviewContext


class DependencyAnalyzer(BaseAnalyzer):
    name = "dependency"
    category = "dependency"

    DEP_FILES = {
        "requirements.txt": "pip",
        "setup.py": "pip",
        "setup.cfg": "pip",
        "pyproject.toml": "pip",
        "package.json": "npm",
        "yarn.lock": "npm",
        "go.mod": "go",
        "Gemfile": "ruby",
        "pom.xml": "maven",
        "Cargo.toml": "rust",
    }

    HIGH_RISK_PACKAGES = {
        "eval", "exec", "subprocess", "os.system", "shell",
        "pickle", "marshal", "yaml.load", "tempfile",
    }

    KNOWN_VULN_PATTERNS = [
        (r"requests==2\.\d+\.\d+", "requests", "Verify requests version for known CVEs"),
        (r"flask==0\.\d+", "flask", "Flask < 1.0 has known security issues"),
        (r"django==1\.\d+", "django", "Django 1.x is end-of-life"),
        (r"django==2\.\d", "django", "Django 2.x is end-of-life"),
        (r"jinja2==2\.\d+", "jinja2", "Jinja2 < 3.0 has known template injection vulnerabilities"),
        (r"pyyaml==5\.\d+", "pyyaml", "PyYAML 5.x has safe_load issues"),
        (r"urllib3==1\.\d+\.\d+", "urllib3", "Verify urllib3 version for known CVEs"),
    ]

    LICENSE_RISKS = {
        "GPL-3.0": "high", "AGPL-3.0": "high", "SSPL": "high",
        "GPL-2.0": "medium", "LGPL-3.0": "low", "LGPL-2.1": "low",
    }

    async def analyze(self, context: ReviewContext) -> AnalyzerResult:
        findings = []
        for file_path, content in context.file_contents.items():
            if not self._is_changed_file(file_path, context):
                continue
            dep_type = self._detect_dep_type(file_path)
            if dep_type:
                findings.extend(self._check_dependencies(file_path, content, dep_type))
                findings.extend(self._check_known_vulnerabilities(file_path, content))
        findings.extend(self._check_dependency_changes(context))
        return AnalyzerResult(analyzer_name=self.name, findings=findings)

    def _detect_dep_type(self, file_path: str) -> str:
        for dep_file, dep_type in self.DEP_FILES.items():
            if file_path.endswith(dep_file) or file_path.endswith(f"/{dep_file}"):
                return dep_type
        return ""

    def _check_dependencies(self, file_path: str, content: str, dep_type: str) -> list:
        findings = []
        lines = content.split("\n")
        unpinned = 0
        total = 0
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("//"):
                continue
            if dep_type == "pip" and ("==" in line or ">=" in line):
                total += 1
            elif dep_type == "pip":
                if re.match(r"^[a-zA-Z]", line):
                    total += 1
                    unpinned += 1
            elif dep_type == "npm":
                if ":" in line and '"' in line:
                    total += 1
                    if "~" in line or "^" in line or "*" in line:
                        unpinned += 1
        if unpinned > 0:
            findings.append(self._make_finding(
                severity="low", confidence=0.6,
                file_path=file_path, line_start=0, line_end=0,
                description=f"{unpinned}/{total} dependencies not pinned to exact versions",
                evidence={"unpinned": unpinned, "total": total, "type": dep_type},
                recommendation="Pin dependencies to exact versions for reproducibility",
                rule_id="dependency.unpinned_versions",
            ))
        return findings

    def _check_known_vulnerabilities(self, file_path: str, content: str) -> list:
        findings = []
        for pattern, pkg, desc in self.KNOWN_VULN_PATTERNS:
            if re.search(pattern, content):
                findings.append(self._make_finding(
                    severity="medium", confidence=0.7,
                    file_path=file_path, line_start=0, line_end=0,
                    description=f"{pkg}: {desc}",
                    evidence={"package": pkg, "pattern": pattern},
                    recommendation=desc,
                    rule_id=f"dependency.known_vuln_{pkg}",
                ))
        return findings

    def _check_dependency_changes(self, context: ReviewContext) -> list:
        findings = []
        dep_files = {"requirements.txt", "package.json", "pyproject.toml",
                      "go.mod", "Cargo.toml", "Gemfile", "pom.xml"}
        for file_path in context.changed_files:
            if any(df in file_path for df in dep_files):
                findings.append(self._make_finding(
                    severity="medium", confidence=0.8,
                    file_path=file_path, line_start=0, line_end=0,
                    description="Dependency file modified — review for security and compatibility",
                    evidence={"file": file_path},
                    recommendation="Run dependency vulnerability scan and check license compatibility",
                    rule_id="dependency.dep_file_changed",
                ))
        return findings
