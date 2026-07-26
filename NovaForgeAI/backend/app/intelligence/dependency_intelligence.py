"""Dependency Intelligence — dependency graph analysis, package health, version drift, license compatibility, supply chain risk."""

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


@dataclass
class DependencyNode:
    name: str
    version: str
    ecosystem: str  # pypi, npm, go, maven, cargo, etc.
    license: str = ""
    latest_version: str = ""
    deprecated: bool = False
    vulnerabilities: list[dict] = field(default_factory=list)
    is_outdated: bool = False
    is_direct: bool = True
    depth: int = 0
    dependencies: list[str] = field(default_factory=list)


@dataclass
class DependencyEdge:
    source: str
    target: str
    version_constraint: str = ""
    is_dev: bool = False
    is_optional: bool = False


@dataclass
class LicenseCompatibility:
    package: str
    license: str
    is_compatible: bool = True
    restrictions: list[str] = field(default_factory=list)


@dataclass
class SupplyChainRisk:
    package: str
    risk_level: str  # low, medium, high, critical
    risk_factors: list[str] = field(default_factory=list)
    recommendation: str = ""


@dataclass
class DependencyReport:
    repo_id: str
    repo_name: str
    timestamp: str
    nodes: list[DependencyNode] = field(default_factory=list)
    edges: list[DependencyEdge] = field(default_factory=list)
    total_dependencies: int = 0
    outdated_count: int = 0
    vulnerable_count: int = 0
    deprecated_count: int = 0
    license_issues: list[LicenseCompatibility] = field(default_factory=list)
    supply_chain_risks: list[SupplyChainRisk] = field(default_factory=list)
    version_drift_score: float = 0.0
    overall_health: float = 0.0


class DependencyIntelligence:
    """Full dependency lifecycle analysis — graph, health, drift, license, supply chain."""

    PYPI_KNOWN = {
        "requests": {"latest": "2.32.3", "license": "Apache-2.0", "deprecated": False},
        "flask": {"latest": "3.1.0", "license": "BSD-3-Clause", "deprecated": False},
        "django": {"latest": "5.1.0", "license": "BSD-3-Clause", "deprecated": False},
        "fastapi": {"latest": "0.115.0", "license": "MIT", "deprecated": False},
        "pydantic": {"latest": "2.9.0", "license": "MIT", "deprecated": False},
        "sqlalchemy": {"latest": "2.0.35", "license": "MIT", "deprecated": False},
        "numpy": {"latest": "2.1.0", "license": "BSD-3-Clause", "deprecated": False},
        "pandas": {"latest": "2.2.2", "license": "BSD-3-Clause", "deprecated": False},
        "pytest": {"latest": "8.3.3", "license": "MIT", "deprecated": False},
        "celery": {"latest": "5.4.0", "license": "BSD-3-Clause", "deprecated": False},
        "redis": {"latest": "5.1.0", "license": "MIT", "deprecated": False},
        "httpx": {"latest": "0.27.2", "license": "BSD-3-Clause", "deprecated": False},
        "aiohttp": {"latest": "3.10.5", "license": "Apache-2.0", "deprecated": False},
        "click": {"latest": "8.1.7", "license": "BSD-3-Clause", "deprecated": False},
        "jinja2": {"latest": "3.1.4", "license": "BSD-3-Clause", "deprecated": False},
        "werkzeug": {"latest": "3.0.3", "license": "BSD-3-Clause", "deprecated": False},
        "gunicorn": {"latest": "22.0.0", "license": "MIT", "deprecated": False},
        "uvicorn": {"latest": "0.30.6", "license": "BSD-3-Clause", "deprecated": False},
        "alembic": {"latest": "1.13.2", "license": "MIT", "deprecated": False},
        "boto3": {"latest": "1.35.0", "license": "Apache-2.0", "deprecated": False},
        "cryptography": {"latest": "43.0.0", "license": "Apache-2.0 / BSD", "deprecated": False},
        "pydantic-settings": {"latest": "2.5.0", "license": "MIT", "deprecated": False},
        "loguru": {"latest": "0.7.2", "license": "MIT", "deprecated": False},
        "rich": {"latest": "13.8.0", "license": "MIT", "deprecated": False},
        "typer": {"latest": "0.12.5", "license": "MIT", "deprecated": False},
    }

    NPM_KNOWN = {
        "react": {"latest": "18.3.1", "license": "MIT", "deprecated": False},
        "vue": {"latest": "3.5.0", "license": "MIT", "deprecated": False},
        "next": {"latest": "14.2.7", "license": "MIT", "deprecated": False},
        "express": {"latest": "4.21.0", "license": "MIT", "deprecated": False},
        "axios": {"latest": "1.7.4", "license": "MIT", "deprecated": False},
        "lodash": {"latest": "4.17.21", "license": "MIT", "deprecated": False},
        "typescript": {"latest": "5.5.4", "license": "Apache-2.0", "deprecated": False},
        "eslint": {"latest": "9.9.0", "license": "MIT", "deprecated": False},
        "prettier": {"latest": "3.3.3", "license": "MIT", "deprecated": False},
        "webpack": {"latest": "5.94.0", "license": "MIT", "deprecated": False},
    }

    KNOWN_VULNERABILITIES = {
        "lodash": [{"cve": "CVE-2024-23346", "severity": "high", "fixed_in": "4.17.21"}],
        "axios": [{"cve": "CVE-2024-39338", "severity": "high", "fixed_in": "1.7.4"}],
        "requests": [{"cve": "CVE-2024-35195", "severity": "medium", "fixed_in": "2.32.0"}],
        "cryptography": [{"cve": "CVE-2024-26130", "severity": "high", "fixed_in": "42.0.4"}],
        "jinja2": [{"cve": "CVE-2024-34064", "severity": "medium", "fixed_in": "3.1.4"}],
        "werkzeug": [{"cve": "CVE-2024-34069", "severity": "medium", "fixed_in": "3.0.3"}],
    }

    LICENSE_RESTRICTIONS = {
        "GPL-2.0": ["Cannot be used in proprietary/closed-source software", "Copyleft — may require source disclosure"],
        "GPL-3.0": ["Cannot be used in proprietary/closed-source software", "Copyleft — may require source disclosure"],
        "AGPL-3.0": ["Cannot be used in proprietary/closed-source software", "Copyleft — network use counted as distribution"],
        "LGPL-2.1": ["May require source disclosure for modifications", "Dynamic linking typically allowed"],
        "LGPL-3.0": ["May require source disclosure for modifications"],
        "MPL-2.0": ["File-level copyleft", "Compatible with proprietary if files not modified"],
        "BSL-1.0": ["No restrictions for most use cases"],
        "Apache-2.0": ["No restrictions for most use cases", "Attribution required"],
        "MIT": ["No restrictions", "Attribution required"],
        "BSD-2-Clause": ["No restrictions", "Attribution required"],
        "BSD-3-Clause": ["No restrictions", "Attribution required"],
        "Unlicense": ["Public domain — no restrictions"],
    }

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)

    def analyze(self) -> DependencyReport:
        report = DependencyReport(
            repo_id=str(hash(str(self.repo_path))),
            repo_name=self.repo_path.name,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        self._analyze_python_deps(report)
        self._analyze_npm_deps(report)
        self._analyze_go_deps(report)

        report.total_dependencies = len(report.nodes)
        report.outdated_count = sum(1 for n in report.nodes if n.is_outdated)
        report.vulnerable_count = sum(1 for n in report.nodes if n.vulnerabilities)
        report.deprecated_count = sum(1 for n in report.nodes if n.deprecated)

        self._check_license_compatibility(report)
        self._assess_supply_chain_risk(report)
        self._calculate_scores(report)

        return report

    def _analyze_python_deps(self, report: DependencyReport):
        req_files = []
        for pattern in ("requirements*.txt", "pyproject.toml", "setup.py", "setup.cfg", "Pipfile"):
            req_files.extend(self.repo_path.glob(pattern))

        parsed = self._parse_requirements(req_files)
        for pkg, ver in parsed.items():
            info = self.PYPI_KNOWN.get(pkg, {})
            pkgs = [v for v in self.KNOWN_VULNERABILITIES.get(pkg, []) if self._version_compare(ver, v.get("fixed_in", "0")) < 0]
            report.nodes.append(DependencyNode(
                name=pkg,
                version=ver.lstrip("^~>=<"),
                ecosystem="pypi",
                license=info.get("license", "Unknown"),
                latest_version=info.get("latest", ""),
                deprecated=info.get("deprecated", False),
                vulnerabilities=pkgs,
                is_outdated=bool(info.get("latest")) and ver.strip("^~>=<! ") != info["latest"],
            ))

    def _parse_requirements(self, files: list[Path]) -> dict[str, str]:
        deps: dict[str, str] = {}
        for f in files:
            if not f.exists():
                continue
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            if f.name == "pyproject.toml":
                try:
                    import tomli
                    data = tomli.loads(content)
                    for section in ("project.dependencies", "project.optional-dependencies", "tool.poetry.dependencies"):
                        keys = section.split(".")
                        section_data = data
                        for k in keys:
                            section_data = section_data.get(k, {})
                            if not isinstance(section_data, dict):
                                break
                        if isinstance(section_data, dict):
                            for pkg_name, pkg_ver in section_data.items():
                                if isinstance(pkg_ver, str) and pkg_name != "python":
                                    deps[pkg_name] = pkg_ver
                                elif isinstance(pkg_ver, dict) and "version" in pkg_ver:
                                    deps[pkg_name] = pkg_ver["version"]
                except (ImportError, tomli.TOMLDecodeError):
                    for match in re.finditer(r'([\w\-_.]+)\s*[=~><!]+\s*[\'"]([^\'"]+)[\'"]', content):
                        deps[match.group(1).lower()] = match.group(2)
            elif f.name.endswith(".txt"):
                for line in content.splitlines():
                    line = line.strip()
                    if line and not line.startswith(("#", "-")) and "==" in line:
                        pkg, ver = line.split("==", 1)
                        deps[pkg.strip().lower()] = ver.strip()
                    elif line and not line.startswith(("#", "-")) and ">=" in line:
                        pkg, ver = line.split(">=", 1)
                        deps[pkg.strip().lower()] = ">=" + ver.strip()
            elif f.suffix == ".cfg":
                for match in re.finditer(r'([\w\-_.]+)\s*=\s*([\w*.]+)', content):
                    deps[match.group(1).lower()] = match.group(2)
        return deps

    def _analyze_npm_deps(self, report: DependencyReport):
        pkg_file = self.repo_path / "package.json"
        if not pkg_file.exists():
            return

        try:
            data = json.loads(pkg_file.read_text())
        except Exception:
            return

        for dep_type in ("dependencies", "devDependencies", "peerDependencies"):
            is_dev = dep_type == "devDependencies"
            deps = data.get(dep_type, {})
            for pkg_name, ver in deps.items():
                info = self.NPM_KNOWN.get(pkg_name, {})
                clean_ver = ver.lstrip("^~>=<")
                pkgs = self.KNOWN_VULNERABILITIES.get(pkg_name, [])
                report.nodes.append(DependencyNode(
                    name=pkg_name,
                    version=clean_ver,
                    ecosystem="npm",
                    license=info.get("license", "Unknown"),
                    latest_version=info.get("latest", ""),
                    deprecated=info.get("deprecated", False),
                    vulnerabilities=pkgs,
                    is_outdated=bool(info.get("latest")) and clean_ver != info["latest"],
                    is_direct=not is_dev,
                    dependencies=[],
                ))

                if dep_type == "dependencies" and is_dev:
                    report.edges.append(DependencyEdge(
                        source=pkg_name, target="", is_dev=True
                    ))

    def _analyze_go_deps(self, report: DependencyReport):
        go_mod = self.repo_path / "go.mod"
        if not go_mod.exists():
            return

        try:
            content = go_mod.read_text()
        except Exception:
            return

        for match in re.finditer(r'^\s+([\w./-]+)\s+v?([\w.+-]+)', content, re.MULTILINE):
            pkg = match.group(1)
            ver = match.group(2)
            report.nodes.append(DependencyNode(
                name=pkg,
                version=ver,
                ecosystem="go",
                license="Unknown",
                latest_version="",
                is_outdated=False,
            ))

    def _check_license_compatibility(self, report: DependencyReport):
        for node in report.nodes:
            lic = node.license
            restrictions = self.LICENSE_RESTRICTIONS.get(lic, [])
            is_compatible = lic in ("MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause",
                                    "Unlicense", "ISC", "CC0-1.0", "BSL-1.0", "MPL-2.0",
                                    "LGPL-2.1", "LGPL-3.0")
            report.license_issues.append(LicenseCompatibility(
                package=node.name,
                license=lic,
                is_compatible=is_compatible,
                restrictions=restrictions,
            ))

    def _assess_supply_chain_risk(self, report: DependencyReport):
        for node in report.nodes:
            risk_factors = []
            risk = "low"

            if node.vulnerabilities:
                risk_factors.append(f"{len(node.vulnerabilities)} known vulnerabilities")
                risk = "high"

            if node.is_outdated:
                risk_factors.append(f"Outdated ({node.version} vs {node.latest_version})")
                risk = "medium" if risk == "low" else risk

            if node.deprecated:
                risk_factors.append("Package is deprecated")
                risk = "critical"

            if node.license == "Unknown":
                risk_factors.append("Unknown license")
                risk = "medium" if risk == "low" else risk

            if node.ecosystem == "npm" and not node.is_direct:
                risk_factors.append("Transitive dependency — harder to audit")
                risk = "medium" if risk == "low" else risk

            if risk_factors:
                report.supply_chain_risks.append(SupplyChainRisk(
                    package=node.name,
                    risk_level=risk,
                    risk_factors=risk_factors,
                    recommendation=f"Update {node.name} to latest version and review its dependency tree",
                ))

    def _calculate_scores(self, report: DependencyReport):
        total = max(report.total_dependencies, 1)

        outdated_ratio = report.outdated_count / total
        vulnerable_ratio = report.vulnerable_count / total
        deprecated_ratio = report.deprecated_count / total
        license_issue_ratio = len([l for l in report.license_issues if not l.is_compatible]) / max(len(report.license_issues), 1)

        report.version_drift_score = max(0, 100 - outdated_ratio * 100 - vulnerable_ratio * 200)
        report.overall_health = max(0, 100 - outdated_ratio * 30 - vulnerable_ratio * 50
                                    - deprecated_ratio * 40 - license_issue_ratio * 20)

    def _version_compare(self, v1: str, v2: str) -> int:
        v1 = v1.lstrip("^~>=<")
        v2 = v2.lstrip("^~>=<")
        try:
            p1 = [int(x) for x in v1.split(".")]
            p2 = [int(x) for x in v2.split(".")]
            for a, b in zip(p1, p2):
                if a < b:
                    return -1
                if a > b:
                    return 1
            return 0
        except (ValueError, AttributeError):
            return 0

    def get_dependency_graph(self, report: DependencyReport) -> dict:
        return {
            "nodes": [
                {"id": n.name, "group": n.ecosystem, "outdated": n.is_outdated,
                 "vulnerable": bool(n.vulnerabilities), "license": n.license}
                for n in report.nodes
            ],
            "links": [
                {"source": e.source, "target": e.target, "dev": e.is_dev}
                for e in report.edges
            ],
        }
