"""Cross-Repository Intelligence — understands relationships across repositories, tracks shared libraries, API contracts, breaking changes, dependency impact, architecture consistency."""

import hashlib
import json
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


@dataclass
class CrossRepoRelationship:
    source_repo: str
    target_repo: str
    relationship_type: str  # depends_on, shares_library, api_consumer, api_provider, fork, related
    shared_artifact: str = ""
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class APIContract:
    provider_repo: str
    consumer_repo: str
    endpoint: str
    method: str = ""
    version: str = ""
    last_verified: str = ""
    is_breaking: bool = False
    breaking_changes: list[str] = field(default_factory=list)


@dataclass
class SharedLibrary:
    name: str
    version: str
    repos: list[str] = field(default_factory=list)
    license: str = ""
    last_sync: str = ""


@dataclass
class BreakingChange:
    library: str
    from_version: str
    to_version: str
    affected_repos: list[str] = field(default_factory=list)
    changes: list[str] = field(default_factory=list)
    estimated_migration_hours: float = 0.0


@dataclass
class CrossRepoReport:
    workspace_id: str
    timestamp: str
    relationships: list[CrossRepoRelationship] = field(default_factory=list)
    api_contracts: list[APIContract] = field(default_factory=list)
    shared_libraries: list[SharedLibrary] = field(default_factory=list)
    breaking_changes: list[BreakingChange] = field(default_factory=list)
    architecture_inconsistencies: list[str] = field(default_factory=list)
    dependency_impact_map: dict[str, list[str]] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)


class CrossRepositoryIntelligence:
    """Cross-repo analysis — relationships, shared libraries, API contracts, breaking changes, architecture consistency."""

    def __init__(self, workspace_path: str):
        self.workspace_path = Path(workspace_path)
        self.repos: list[Path] = []

    def discover_repositories(self) -> list[Path]:
        self.repos = [d for d in self.workspace_path.iterdir()
                      if d.is_dir() and not d.name.startswith(".") and
                      ((d / ".git").exists() or (d / "requirements.txt").exists() or (d / "pyproject.toml").exists())]
        return self.repos

    def analyze(self) -> CrossRepoReport:
        if not self.repos:
            self.discover_repositories()

        report = CrossRepoReport(
            workspace_id=str(hash(str(self.workspace_path))),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        self._discover_relationships(report)
        self._analyze_shared_libraries(report)
        self._detect_api_contracts(report)
        self._detect_breaking_changes(report)
        self._analyze_architecture_consistency(report)
        self._build_dependency_impact_map(report)
        self._generate_recommendations(report)

        return report

    def _discover_relationships(self, report: CrossRepoReport):
        for repo in self.repos:
            pyproject = repo / "pyproject.toml"
            if pyproject.exists():
                try:
                    content = pyproject.read_text()
                    for other in self.repos:
                        if other.name == repo.name:
                            continue
                        if other.name in content:
                            report.relationships.append(CrossRepoRelationship(
                                source_repo=repo.name,
                                target_repo=other.name,
                                relationship_type="depends_on",
                                shared_artifact=other.name,
                                confidence=0.8,
                            ))
                except Exception:
                    pass

        for repo in self.repos:
            for f in repo.rglob("*.py"):
                try:
                    content = f.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                for other in self.repos:
                    if other.name == repo.name:
                        continue
                    if f"from {other.name}" in content or f"import {other.name}" in content:
                        report.relationships.append(CrossRepoRelationship(
                            source_repo=repo.name,
                            target_repo=other.name,
                            relationship_type="api_consumer",
                            shared_artifact=str(f.relative_to(repo)),
                            confidence=0.9,
                        ))

    def _analyze_shared_libraries(self, report: CrossRepoReport):
        all_deps: dict[str, dict] = defaultdict(lambda: {"versions": [], "repos": []})

        for repo in self.repos:
            req_file = repo / "requirements.txt"
            if req_file.exists():
                try:
                    for line in req_file.read_text().splitlines():
                        if "==" in line:
                            pkg, ver = line.split("==", 1)
                            all_deps[pkg.strip().lower()]["versions"].append(ver.strip())
                            all_deps[pkg.strip().lower()]["repos"].append(repo.name)
                except Exception:
                    pass

        for pkg, info in all_deps.items():
            if len(info["repos"]) > 1:
                report.shared_libraries.append(SharedLibrary(
                    name=pkg,
                    version=max(set(info["versions"]), key=info["versions"].count) if info["versions"] else "",
                    repos=list(set(info["repos"])),
                ))

    def _detect_api_contracts(self, report: CrossRepoReport):
        api_repos = []
        for repo in self.repos:
            for f in repo.rglob("*.py"):
                try:
                    content = f.read_text(encoding="utf-8", errors="ignore")
                    if re.search(r"@(?:app|router)\.(?:get|post|put|delete|patch)", content):
                        api_repos.append(repo)
                        break
                except Exception:
                    pass

        for provider in api_repos:
            for consumer in self.repos:
                if consumer.name == provider.name:
                    continue
                try:
                    for f in consumer.rglob("*.py"):
                        content = f.read_text(encoding="utf-8", errors="ignore")
                        if provider.name in content and ("requests." in content or "httpx." in content or "aiohttp." in content):
                            report.api_contracts.append(APIContract(
                                provider_repo=provider.name,
                                consumer_repo=consumer.name,
                                endpoint=f"api/{provider.name}",
                                last_verified=datetime.now(timezone.utc).isoformat()[:10],
                            ))
                            break
                except Exception:
                    pass

    def _detect_breaking_changes(self, report: CrossRepoReport):
        for shared in report.shared_libraries:
            version_nums = [v for v in shared.repos if v]
            if len(version_nums) >= 2:
                major_versions = set()
                for v in version_nums:
                    try:
                        major_versions.add(int(v.split(".")[0]))
                    except (ValueError, IndexError):
                        pass
                if len(major_versions) > 1:
                    report.breaking_changes.append(BreakingChange(
                        library=shared.name,
                        from_version=min(version_nums),
                        to_version=max(version_nums),
                        affected_repos=shared.repos,
                        changes=[f"Major version difference detected across repos"],
                        estimated_migration_hours=len(shared.repos) * 2.0,
                    ))

    def _analyze_architecture_consistency(self, report: CrossRepoReport):
        patterns_by_repo: dict[str, set[str]] = defaultdict(set)

        for repo in self.repos:
            for f in repo.rglob("*.py"):
                try:
                    content = f.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                if re.search(r"class\s+\w+Service", content):
                    patterns_by_repo[repo.name].add("service_layer")
                if re.search(r"class\s+\w+Repository", content):
                    patterns_by_repo[repo.name].add("repository_pattern")
                if re.search(r"@app\.(?:get|post|put|delete|patch)", content):
                    patterns_by_repo[repo.name].add("rest_api")
                if re.search(r"class\s+\w+Event|def publish_\w+|def handle_\w+", content):
                    patterns_by_repo[repo.name].add("event_driven")

        if patterns_by_repo:
            all_patterns = set()
            for patterns in patterns_by_repo.values():
                all_patterns.update(patterns)
            for pattern in sorted(all_patterns):
                repos_with = [r for r, p in patterns_by_repo.items() if pattern in p]
                repos_without = [r for r in patterns_by_repo.keys() if r not in repos_with]
                if len(repos_without) > 1 and len(repos_with) > 1:
                    report.architecture_inconsistencies.append(
                        f"Pattern '{pattern}' used in {len(repos_with)} repos but missing in {len(repos_without)}"
                    )

    def _build_dependency_impact_map(self, report: CrossRepoReport):
        impact_map = defaultdict(list)
        for rel in report.relationships:
            if rel.relationship_type in ("depends_on", "api_consumer"):
                impact_map[rel.target_repo].append(rel.source_repo)
        report.dependency_impact_map = dict(impact_map)

    def _generate_recommendations(self, report: CrossRepoReport):
        if report.breaking_changes:
            for bc in report.breaking_changes:
                report.recommendations.append(
                    f"Breaking change in {bc.library}: {len(bc.affected_repos)} repos need migration (~{bc.estimated_migration_hours}h)"
                )
        if report.architecture_inconsistencies:
            for inc in report.architecture_inconsistencies[:3]:
                report.recommendations.append(f"Architecture inconsistency: {inc}")
        if not report.relationships:
            report.recommendations.append("No cross-repository relationships detected — verify workspace structure")

    def get_impact_analysis(self, repo_name: str, report: CrossRepoReport) -> dict:
        impacted = []
        for rel in report.relationships:
            if rel.target_repo == repo_name or rel.source_repo == repo_name:
                impacted.append({
                    "source": rel.source_repo,
                    "target": rel.target_repo,
                    "type": rel.relationship_type,
                    "artifact": rel.shared_artifact,
                })
        return {
            "repo": repo_name,
            "direct_dependents": report.dependency_impact_map.get(repo_name, []),
            "direct_dependencies": [
                rel.target_repo for rel in report.relationships
                if rel.source_repo == repo_name
            ],
            "all_relationships": impacted,
        }
