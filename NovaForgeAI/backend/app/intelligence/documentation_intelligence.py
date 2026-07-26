"""Documentation Intelligence — automatically analyzes, generates, and improves repository documentation."""

import ast
import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from enum import Enum


class DocType(Enum):
    README = "readme"
    ARCHITECTURE = "architecture"
    API = "api"
    SETUP = "setup"
    DEVELOPER = "developer"
    COMMENT = "comment"
    ADR = "adr"
    RELEASE_NOTES = "release_notes"
    CONTRIBUTING = "contributing"
    CHANGELOG = "changelog"


@dataclass
class DocGap:
    file: str
    type: DocType
    severity: str  # critical, high, medium, low
    description: str
    suggested_content: str = ""
    confidence: float = 0.0


@dataclass
class DocSection:
    title: str
    content: str
    source: str = "generated"


@dataclass
class DocumentationReport:
    repo_id: str
    repo_name: str
    timestamp: str
    gaps: list[DocGap] = field(default_factory=list)
    generated_docs: list[DocSection] = field(default_factory=list)
    documentation_coverage: float = 0.0
    completeness_score: float = 0.0
    recommendations: list[dict] = field(default_factory=list)


class DocumentationIntelligence:
    """Analyzes documentation gaps and generates missing documentation automatically."""

    REQUIRED_SECTIONS = {
        DocType.README: [
            "Project Title / Description", "Installation", "Usage / Quick Start",
            "Configuration", "API Reference", "Contributing", "License",
        ],
        DocType.ARCHITECTURE: [
            "System Overview", "Component Diagram", "Data Flow",
            "Technology Stack", "Deployment Architecture",
        ],
        DocType.API: [
            "Endpoints", "Authentication", "Request/Response Format",
            "Error Codes", "Rate Limiting",
        ],
        DocType.SETUP: [
            "Prerequisites", "Environment Setup", "Installation Steps",
            "Configuration", "Verification",
        ],
        DocType.DEVELOPER: [
            "Development Environment", "Code Style", "Testing",
            "Building", "Debugging", "Deployment",
        ],
    }

    SECTION_PATTERNS: dict[str, list[str]] = {
        DocType.README.value: [
            r"^#\s+.+", r"(?i)install", r"(?i)usage", r"(?i)(quick\s*start|getting\s*started)",
            r"(?i)configure", r"(?i)(api|reference)", r"(?i)contributing", r"(?i)license",
        ],
        DocType.ARCHITECTURE.value: [
            r"(?i)(overview|architecture)", r"(?i)(component|diagram)", r"(?i)(data\s*flow|flow)",
            r"(?i)(tech\s*stack|technology)", r"(?i)(deploy|deployment)",
        ],
    }

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)

    def analyze(self) -> DocumentationReport:
        report = DocumentationReport(
            repo_id=str(hash(str(self.repo_path))),
            repo_name=self.repo_path.name,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        self._analyze_readme(report)
        self._analyze_architecture_docs(report)
        self._analyze_api_docs(report)
        self._analyze_setup_guide(report)
        self._analyze_developer_guide(report)
        self._analyze_code_comments(report)
        self._generate_missing_documentation(report)

        total_sections = sum(len(v) for v in self.REQUIRED_SECTIONS.values())
        found_sections = 0
        for gaps in report.gaps:
            if gaps.confidence < 0.3:
                found_sections += 1

        report.documentation_coverage = min(100, (1 - len(report.gaps) / max(total_sections, 1)) * 100)
        report.completeness_score = report.documentation_coverage
        report.recommendations = self._generate_doc_recommendations(report)

        return report

    def _analyze_readme(self, report: DocumentationReport):
        readme_path = self.repo_path / "README.md"
        if not readme_path.exists():
            report.gaps.append(DocGap(
                file="README.md",
                type=DocType.README,
                severity="critical",
                description="Missing README.md — the most important documentation file",
                confidence=1.0,
            ))
            return

        content = readme_path.read_text(encoding="utf-8", errors="ignore")
        for section in self.REQUIRED_SECTIONS[DocType.README]:
            section_content = content.lower()
            keywords = section.lower().split()
            found = any(kw in section_content for kw in keywords)
            if not found:
                report.gaps.append(DocGap(
                    file="README.md",
                    type=DocType.README,
                    severity="high" if section in ("Installation", "Usage / Quick Start") else "medium",
                    description=f"README is missing '{section}' section",
                    suggested_content=self._generate_readme_section(section),
                    confidence=0.7,
                ))

    def _analyze_architecture_docs(self, report: DocumentationReport):
        arch_files = list(self.repo_path.rglob("ARCHITECTURE*")) + list(self.repo_path.rglob("architecture*"))
        if not arch_files:
            report.gaps.append(DocGap(
                file="ARCHITECTURE.md",
                type=DocType.ARCHITECTURE,
                severity="high",
                description="Missing architecture documentation",
                suggested_content=self._generate_architecture_doc(),
                confidence=0.6,
            ))
        else:
            for af in arch_files:
                content = af.read_text(encoding="utf-8", errors="ignore")
                for section in self.REQUIRED_SECTIONS[DocType.ARCHITECTURE]:
                    if section.lower()[:10] not in content.lower():
                        report.gaps.append(DocGap(
                            file=str(af.relative_to(self.repo_path)),
                            type=DocType.ARCHITECTURE,
                            severity="medium",
                            description=f"Architecture doc missing '{section}' section",
                            confidence=0.5,
                        ))

    def _analyze_api_docs(self, report: DocumentationReport):
        api_files = list(self.repo_path.rglob("api*.md")) + list(self.repo_path.rglob("*api*.md"))
        has_apidocs = bool(api_files) or bool(list(self.repo_path.rglob("openapi*.json"))) or \
                     bool(list(self.repo_path.rglob("openapi*.yaml")))

        has_api_endpoints = False
        for f in self.repo_path.rglob("*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                if re.search(r'@app\.(?:get|post|put|delete|patch|router)', content):
                    has_api_endpoints = True
                    break
            except Exception:
                continue

        if has_api_endpoints and not has_apidocs:
            report.gaps.append(DocGap(
                file="API.md",
                type=DocType.API,
                severity="high",
                description="API endpoints detected but no API documentation found",
                suggested_content=self._generate_api_doc(),
                confidence=0.5,
            ))

    def _analyze_setup_guide(self, report: DocumentationReport):
        has_setup = bool(list(self.repo_path.rglob("SETUP*"))) or bool(list(self.repo_path.rglob("setup*guide*")))

        env_files = list(self.repo_path.glob(".env*")) + list(self.repo_path.glob(".env.sample")) + \
                   list(self.repo_path.glob(".env.example"))
        if not has_setup:
            report.gaps.append(DocGap(
                file="SETUP.md",
                type=DocType.SETUP,
                severity="medium",
                description="Missing setup/installation guide",
                suggested_content=self._generate_setup_guide(),
                confidence=0.5,
            ))

    def _analyze_developer_guide(self, report: DocumentationReport):
        contributing = self.repo_path / "CONTRIBUTING.md"
        has_dev_guide = contributing.exists() or bool(list(self.repo_path.rglob("DEVELOPER*")))

        if not has_dev_guide and (self.repo_path / ".github/workflows").exists():
            report.gaps.append(DocGap(
                file="CONTRIBUTING.md",
                type=DocType.DEVELOPER,
                severity="medium",
                description="Missing contributing/developer guide",
                suggested_content=self._generate_contributing_guide(),
                confidence=0.4,
            ))

    def _analyze_code_comments(self, report: DocumentationReport):
        for f in self.repo_path.rglob("*.py"):
            if f.name == "__init__.py":
                continue
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(content)
            except Exception:
                continue
            rel = str(f.relative_to(self.repo_path))

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    has_docstring = ast.get_docstring(node) is not None
                    if not has_docstring and not node.name.startswith("_"):
                        report.gaps.append(DocGap(
                            file=rel,
                            type=DocType.COMMENT,
                            severity="low",
                            description=f"Missing docstring for function `{node.name}`",
                            suggested_content=f"    \"\"\"{node.name} — TODO: add description.\n\n"
                                              f"    Args:\n        TODO: add args.\n"
                                              f"    Returns:\n        TODO: add return type.\n    \"\"\"",
                            confidence=0.8,
                        ))
                elif isinstance(node, ast.ClassDef):
                    has_docstring = ast.get_docstring(node) is not None
                    if not has_docstring:
                        report.gaps.append(DocGap(
                            file=rel,
                            type=DocType.COMMENT,
                            severity="low",
                            description=f"Missing docstring for class `{node.name}`",
                            suggested_content=f"\"\"\"{node.name} — TODO: add class description.\n\"\"\"",
                            confidence=0.8,
                        ))

        if len(report.gaps) > 100:
            report.gaps = report.gaps[:100]

    def _generate_missing_documentation(self, report: DocumentationReport):
        for gap in report.gaps:
            if gap.type == DocType.README and not (self.repo_path / "README.md").exists():
                report.generated_docs.append(DocSection(
                    title="README.md",
                    content=self._generate_full_readme(),
                    source="generated",
                ))
            elif gap.type == DocType.ARCHITECTURE and not list(self.repo_path.rglob("ARCHITECTURE*")):
                report.generated_docs.append(DocSection(
                    title="ARCHITECTURE.md",
                    content=self._generate_architecture_doc(),
                    source="generated",
                ))
            elif gap.type == DocType.CONTRIBUTING and not (self.repo_path / "CONTRIBUTING.md").exists():
                report.generated_docs.append(DocSection(
                    title="CONTRIBUTING.md",
                    content=self._generate_contributing_guide(),
                    source="generated",
                ))

    def _generate_readme_section(self, section: str) -> str:
        templates = {
            "Project Title / Description": f"# {self.repo_path.name}\n\nTODO: Add project description\n",
            "Installation": "## Installation\n\n```bash\n# TODO: Add installation instructions\npip install -r requirements.txt\n```\n",
            "Usage / Quick Start": "## Usage\n\n```python\n# TODO: Add usage example\n```\n",
            "Configuration": "## Configuration\n\n| Variable | Description | Default |\n|----------|-------------|--------|\n| `TODO` | TODO | `-` |\n",
            "API Reference": "## API Reference\n\n### `TODO`\n- **Endpoint**: `TODO`\n- **Method**: `GET/POST/PUT/DELETE`\n- **Auth**: `TODO`\n",
            "Contributing": "## Contributing\n\nPlease see [CONTRIBUTING.md](CONTRIBUTING.md) for details.\n",
            "License": "## License\n\nMIT License. See [LICENSE](LICENSE) for details.\n",
        }
        return templates.get(section, f"## {section}\n\nTODO: Add content\n")

    def _generate_full_readme(self) -> str:
        detected_lang = "Python"
        if (self.repo_path / "package.json").exists():
            detected_lang = "Node.js"

        return (
            f"# {self.repo_path.name}\n\n"
            f"## Overview\n\nTODO: Add project description\n\n"
            f"## 🚀 Quick Start\n\n"
            f"### Prerequisites\n\n"
            f"- {detected_lang} 3.10+\n- pip\n\n"
            f"### Installation\n\n"
            f"```bash\ngit clone https://github.com/org/{self.repo_path.name}.git\n"
            f"cd {self.repo_path.name}\npip install -r requirements.txt\n```\n\n"
            f"## 📖 Usage\n\n```python\n# TODO: Add usage example\n```\n\n"
            f"## 🏗 Architecture\n\nSee [ARCHITECTURE.md](ARCHITECTURE.md) for system design.\n\n"
            f"## 📚 API\n\nSee [API.md](API.md) for API reference.\n\n"
            f"## 🧪 Testing\n\n```bash\npytest\n```\n\n"
            f"## 🤝 Contributing\n\nPlease read [CONTRIBUTING.md](CONTRIBUTING.md).\n\n"
            f"## 📄 License\n\nMIT License — see [LICENSE](LICENSE).\n"
        )

    def _generate_architecture_doc(self) -> str:
        return (
            f"# Architecture — {self.repo_path.name}\n\n"
            "## Overview\n\n"
            "TODO: Describe the high-level architecture of this project.\n\n"
            "## Technology Stack\n\n"
            "| Component | Technology |\n"
            "|-----------|-----------|\n"
            "| Backend | TODO |\n"
            "| Frontend | TODO |\n"
            "| Database | TODO |\n"
            "| Cache | TODO |\n"
            "| Queue | TODO |\n"
            "| CI/CD | TODO |\n\n"
            "## Component Diagram\n\n"
            "```\nTODO: Add component diagram\n```\n\n"
            "## Data Flow\n\n"
            "1. TODO: Describe request flow\n"
            "2. TODO: Describe data processing\n"
            "3. TODO: Describe response flow\n\n"
            "## Deployment Architecture\n\n"
            "```\nTODO: Add deployment diagram\n```\n"
        )

    def _generate_api_doc(self) -> str:
        return (
            "## API Reference\n\n"
            "### Authentication\n\n"
            "TODO: Describe authentication method\n\n"
            "### Endpoints\n\n"
            "| Method | Path | Description | Auth |\n"
            "|--------|------|-------------|------|\n"
            "| GET | `/api/v1/health` | Health check | None |\n"
            "| TODO | `/api/v1/*` | TODO | TODO |\n\n"
            "### Request/Response Format\n\n"
            "```json\n{\n  \"status\": \"ok\",\n  \"data\": {}\n}\n```\n"
        )

    def _generate_setup_guide(self) -> str:
        return (
            "## Setup Guide\n\n"
            "### Prerequisites\n\n"
            "- Python 3.10+\n- PostgreSQL (or other database)\n- Redis (optional)\n\n"
            "### Environment Setup\n\n"
            "```bash\ncp .env.example .env\n# Edit .env with your configuration\n```\n\n"
            "### Installation\n\n"
            "```bash\npython -m venv venv\n"
            "source venv/bin/activate  # On Windows: venv\\Scripts\\activate\n"
            "pip install -r requirements.txt\n"
            "python -m app.db.migrate\n```\n\n"
            "### Verification\n\n"
            "```bash\npytest\nuvicorn app.main:app --reload\n# Visit http://localhost:8000/health\n```\n"
        )

    def _generate_contributing_guide(self) -> str:
        return (
            "# Contributing\n\n"
            "## Development Setup\n\n"
            "1. Fork the repository\n"
            "2. Create a feature branch: `git checkout -b feature/my-feature`\n"
            "3. Install development dependencies: `pip install -r requirements-dev.txt`\n"
            "4. Make your changes\n"
            "5. Run tests: `pytest`\n"
            "6. Run linter: `ruff check .`\n"
            "7. Commit and push\n\n"
            "## Code Style\n\n"
            "- Follow PEP 8\n"
            - "Use type hints\n"
            - "Write docstrings for all public APIs\n"
            - "Keep functions focused and under 50 lines\n\n"
            "## Pull Request Process\n\n"
            "1. Update documentation if needed\n"
            "2. Add tests for new functionality\n"
            "3. Ensure all tests pass\n"
            "4. Request review from maintainers\n\n"
            "## Code of Conduct\n\n"
            "Please note that this project has a Code of Conduct. By participating, you agree to uphold it.\n"
        )

    def _generate_doc_recommendations(self, report: DocumentationReport) -> list[dict]:
        recs = []
        critical_gaps = [g for g in report.gaps if g.severity == "critical"]
        if critical_gaps:
            recs.append({
                "priority": "critical",
                "area": "documentation",
                "message": f"Missing critical documentation: {', '.join(g.file for g in critical_gaps[:3])}",
                "action": "Create the missing documents immediately",
            })

        high_gaps = [g for g in report.gaps if g.severity == "high"]
        if high_gaps:
            recs.append({
                "priority": "high",
                "area": "documentation",
                "message": f"{len(high_gaps)} high-priority documentation gaps found",
                "action": "Generate the missing sections using the suggested content templates",
            })

        if report.generated_docs:
            recs.append({
                "priority": "medium",
                "area": "documentation",
                "message": f"Generated {len(report.generated_docs)} documentation files automatically",
                "action": "Review and customize the auto-generated documentation",
            })

        return recs
