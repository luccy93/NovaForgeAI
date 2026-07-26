"""AI Knowledge Engine — continuously builds engineering, repository, architecture, organization, documentation, developer, and historical knowledge."""

import hashlib
import json
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional


class KnowledgeDomain(Enum):
    ENGINEERING = "engineering"
    REPOSITORY = "repository"
    ARCHITECTURE = "architecture"
    ORGANIZATION = "organization"
    DOCUMENTATION = "documentation"
    DEVELOPER = "developer"
    HISTORICAL = "historical"


@dataclass
class KnowledgeItem:
    id: str
    domain: KnowledgeDomain
    key: str
    value: Any
    source: str = ""
    confidence: float = 1.0
    version: int = 1
    tags: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class KnowledgeGraph:
    entities: dict[str, dict] = field(default_factory=dict)
    relationships: list[dict] = field(default_factory=list)


class AIKnowledgeEngine:
    """Continuously builds and maintains structured knowledge across all domains."""

    def __init__(self, repo_path: str = ""):
        self.repo_path = Path(repo_path) if repo_path else Path()
        self.knowledge: dict[str, KnowledgeItem] = {}
        self.graph = KnowledgeGraph()
        self._history: list[dict] = []

    def learn(self, domain: KnowledgeDomain, key: str, value: Any, source: str = "",
              confidence: float = 1.0, tags: list[str] = None) -> KnowledgeItem:
        skey = f"{domain.value}:{key}"
        if skey in self.knowledge:
            item = self.knowledge[skey]
            old_value = item.value
            item.value = value
            item.source = source or item.source
            item.confidence = max(item.confidence, confidence)
            item.version += 1
            item.updated_at = datetime.now(timezone.utc).isoformat()
            if tags:
                item.tags = list(set(item.tags + tags))
            self._history.append({
                "key": skey, "old_value": old_value, "new_value": value,
                "timestamp": item.updated_at, "version": item.version,
            })
        else:
            item = KnowledgeItem(
                id=f"k-{uuid.uuid4().hex[:12]}",
                domain=domain, key=key, value=value,
                source=source, confidence=confidence,
                tags=tags or [],
                created_at=datetime.now(timezone.utc).isoformat(),
                updated_at=datetime.now(timezone.utc).isoformat(),
            )
            self.knowledge[skey] = item
        return item

    def get(self, domain: KnowledgeDomain, key: str) -> Optional[Any]:
        item = self.knowledge.get(f"{domain.value}:{key}")
        return item.value if item else None

    def query(self, domain: Optional[KnowledgeDomain] = None, tag: str = "",
              min_confidence: float = 0.0) -> list[KnowledgeItem]:
        results = list(self.knowledge.values())
        if domain:
            results = [r for r in results if r.domain == domain]
        if tag:
            results = [r for r in results if tag in r.tags]
        if min_confidence > 0:
            results = [r for r in results if r.confidence >= min_confidence]
        return sorted(results, key=lambda x: x.confidence, reverse=True)

    def build_engineering_knowledge(self):
        """Build knowledge about the engineering practices in the repo."""
        for f in self.repo_path.rglob("*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            rel = str(f.relative_to(self.repo_path))

            if "pytest" in content:
                self.learn(KnowledgeDomain.ENGINEERING, "test_framework", "pytest",
                           source=rel, confidence=0.8, tags=["testing"])
            if "unittest" in content:
                self.learn(KnowledgeDomain.ENGINEERING, "test_framework", "unittest",
                           source=rel, confidence=0.8, tags=["testing"])
            if "async def" in content:
                self.learn(KnowledgeDomain.ENGINEERING, "async_usage", True,
                           source=rel, confidence=0.7, tags=["async"])
            if "type hint" in content.lower() or "def " in content and ":" in content.split("def ")[1][:100]:
                self.learn(KnowledgeDomain.ENGINEERING, "type_hints", True,
                           source=rel, confidence=0.6, tags=["types"])
            break

    def build_repository_knowledge(self):
        """Build knowledge about the repository structure and composition."""
        self.learn(KnowledgeDomain.REPOSITORY, "name", self.repo_path.name, confidence=1.0)
        self.learn(KnowledgeDomain.REPOSITORY, "path", str(self.repo_path.absolute()), confidence=1.0)

        py_files = len(list(self.repo_path.rglob("*.py")))
        js_files = len(list(self.repo_path.rglob("*.js")))
        md_files = len(list(self.repo_path.rglob("*.md")))
        total = py_files + js_files

        self.learn(KnowledgeDomain.REPOSITORY, "python_files", py_files, tags=["stats"])
        self.learn(KnowledgeDomain.REPOSITORY, "javascript_files", js_files, tags=["stats"])
        self.learn(KnowledgeDomain.REPOSITORY, "doc_files", md_files, tags=["stats"])
        self.learn(KnowledgeDomain.REPOSITORY, "total_source_files", total, tags=["stats"])

        top_dirs = [d.name for d in self.repo_path.iterdir() if d.is_dir() and not d.name.startswith(".")]
        self.learn(KnowledgeDomain.REPOSITORY, "top_level_directories", top_dirs, tags=["structure"])

        if (self.repo_path / "requirements.txt").exists():
            self.learn(KnowledgeDomain.REPOSITORY, "package_manager", "pip", tags=["dependencies"])
        if (self.repo_path / "pyproject.toml").exists():
            self.learn(KnowledgeDomain.REPOSITORY, "package_manager", "poetry/pdm", tags=["dependencies"])
        if (self.repo_path / "package.json").exists():
            self.learn(KnowledgeDomain.REPOSITORY, "package_manager", "npm/yarn", tags=["dependencies"])

    def build_architecture_knowledge(self):
        """Build knowledge about the architecture patterns used."""
        patterns_found = []
        for f in self.repo_path.rglob("*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            if re.search(r"class\s+\w+Service", content):
                patterns_found.append("service_layer")
            if re.search(r"@app\.(?:get|post|put|delete|patch|router)", content):
                patterns_found.append("rest_api")
            if re.search(r"class\s+\w+Repository", content):
                patterns_found.append("repository_pattern")
            if re.search(r"class\s+\w+Middleware", content):
                patterns_found.append("middleware")
            if re.search(r"class\s+\w+Event|def publish_\w+|def handle_\w+", content):
                patterns_found.append("event_driven")
            if re.search(r"async\s+def|asyncio\.run", content):
                patterns_found.append("async")
            if re.search(r"BaseModel|pydantic", content):
                patterns_found.append("validation_layer")

        if patterns_found:
            self.learn(KnowledgeDomain.ARCHITECTURE, "patterns", list(set(patterns_found)),
                       confidence=0.8, tags=["architecture", "patterns"])

        docker = (self.repo_path / "Dockerfile").exists()
        compose = (self.repo_path / "docker-compose.yml").exists()
        ci = (self.repo_path / ".github/workflows").exists()
        self.learn(KnowledgeDomain.ARCHITECTURE, "containerization", docker, tags=["infra"])
        self.learn(KnowledgeDomain.ARCHITECTURE, "orchestration", compose, tags=["infra"])
        self.learn(KnowledgeDomain.ARCHITECTURE, "ci_cd", ci, tags=["infra"])

    def build_organization_knowledge(self):
        """Build knowledge about organizational conventions."""
        configs = {
            "editorconfig": ".editorconfig", "precommit": ".pre-commit-config.yaml",
            "flake8": ".flake8", "ruff": "ruff.toml", "mypy": "mypy.ini",
        }
        found_configs = [name for name, path in configs.items() if (self.repo_path / path).exists()]
        if found_configs:
            self.learn(KnowledgeDomain.ORGANIZATION, "code_quality_tools", found_configs,
                       confidence=0.9, tags=["tooling"])

        if (self.repo_path / "CONTRIBUTING.md").exists():
            self.learn(KnowledgeDomain.ORGANIZATION, "has_contributing_guide", True, tags=["process"])
        if (self.repo_path / "CODE_OF_CONDUCT.md").exists():
            self.learn(KnowledgeDomain.ORGANIZATION, "has_code_of_conduct", True, tags=["process"])
        if (self.repo_path / "LICENSE").exists():
            try:
                license_text = (self.repo_path / "LICENSE").read_text()[:100]
                self.learn(KnowledgeDomain.ORGANIZATION, "license", license_text[:50], tags=["legal"])
            except Exception:
                pass

    def build_documentation_knowledge(self):
        """Build knowledge about documentation coverage."""
        readme = self.repo_path / "README.md"
        if readme.exists():
            content = readme.read_text(encoding="utf-8", errors="ignore")
            sections = re.findall(r'^##\s+(.+)', content, re.MULTILINE)
            self.learn(KnowledgeDomain.DOCUMENTATION, "readme_sections", sections,
                       source="README.md", confidence=0.9, tags=["readme"])

        doc_files = list(self.repo_path.rglob("*.md"))
        self.learn(KnowledgeDomain.DOCUMENTATION, "doc_file_count", len(doc_files), tags=["stats"])

        doc_dirs = [d.name for d in self.repo_path.iterdir() if d.is_dir() and d.name in ("docs", "wiki")]
        if doc_dirs:
            self.learn(KnowledgeDomain.DOCUMENTATION, "doc_directories", doc_dirs, tags=["structure"])

        docstring_count = 0
        total_funcs = 0
        for f in self.repo_path.rglob("*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                total_funcs += len(re.findall(r'def\s+\w+\(', content))
                docstring_count += len(re.findall(r'""".*?"""', content, re.DOTALL))
            except Exception:
                pass
        if total_funcs > 0:
            ratio = docstring_count / max(total_funcs, 1)
            self.learn(KnowledgeDomain.DOCUMENTATION, "docstring_ratio", round(ratio, 3), tags=["quality"])

    def build_developer_knowledge(self):
        """Build knowledge about developer patterns and practices."""
        developers = set()
        for f in self.repo_path.rglob("*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                for match in re.finditer(r'#\s*@(?:author|created_by):?\s*(.+)', content, re.IGNORECASE):
                    developers.add(match.group(1).strip())
            except Exception:
                pass

        if developers:
            self.learn(KnowledgeDomain.DEVELOPER, "known_developers", list(developers), tags=["people"])

        total_commits = 0
        try:
            git_dir = self.repo_path / ".git"
            if git_dir.exists():
                import subprocess
                result = subprocess.run(
                    ["git", "shortlog", "-sn"],
                    cwd=self.repo_path, capture_output=True, text=True, timeout=5
                )
                for line in result.stdout.splitlines():
                    if line.strip():
                        total_commits += 1
                self.learn(KnowledgeDomain.DEVELOPER, "commit_activity", total_commits, tags=["activity"])
        except Exception:
            pass

    def build_historical_knowledge(self):
        """Build knowledge from historical patterns in the knowledge base."""
        if self._history:
            self.learn(KnowledgeDomain.HISTORICAL, "knowledge_evolution", {
                "total_updates": len(self._history),
                "most_updated": max(set(h["key"] for h in self._history),
                                   key=lambda k: sum(1 for h in self._history if h["key"] == k)),
                "first_recorded": self._history[0]["timestamp"],
                "last_recorded": self._history[-1]["timestamp"],
            }, confidence=0.9, tags=["history"])

    def build_all(self):
        """Build knowledge across all domains."""
        self.build_engineering_knowledge()
        self.build_repository_knowledge()
        self.build_architecture_knowledge()
        self.build_organization_knowledge()
        self.build_documentation_knowledge()
        self.build_developer_knowledge()
        self.build_historical_knowledge()

    def add_relationship(self, source_id: str, target_id: str, rel_type: str, properties: dict = None):
        self.graph.relationships.append({
            "source": source_id, "target": target_id,
            "type": rel_type, "properties": properties or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def search(self, query: str, domain: Optional[KnowledgeDomain] = None, limit: int = 20) -> list[KnowledgeItem]:
        results = []
        for item in self.knowledge.values():
            if domain and item.domain != domain:
                continue
            if query.lower() in str(item.key).lower() or query.lower() in str(item.value).lower():
                results.append(item)
            elif any(query.lower() in t.lower() for t in item.tags):
                results.append(item)
        return sorted(results, key=lambda x: x.confidence, reverse=True)[:limit]

    def get_domain_summary(self) -> dict[str, dict]:
        summary = defaultdict(lambda: {"count": 0, "avg_confidence": 0.0, "tags": set()})
        for item in self.knowledge.values():
            domain = item.domain.value
            summary[domain]["count"] += 1
            summary[domain]["avg_confidence"] += item.confidence
            summary[domain]["tags"].update(item.tags)
        for v in summary.values():
            v["avg_confidence"] = round(v["avg_confidence"] / max(v["count"], 1), 3)
            v["tags"] = sorted(v["tags"])
        return dict(summary)

    def export_knowledge_base(self) -> dict:
        return {
            "items": {k: v.__dict__ for k, v in self.knowledge.items()},
            "graph": self.graph.__dict__,
            "history_count": len(self._history),
            "exported_at": datetime.now(timezone.utc).isoformat(),
        }


import re  # noqa: E402
