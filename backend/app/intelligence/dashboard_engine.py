"""Dashboard Engine — generates structured dashboards for executive, engineering, repository, architecture, security, AI, and DevOps views."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


@dataclass
class DashboardCard:
    id: str
    title: str
    value: Any
    unit: str = ""
    trend: str = "stable"  # up, down, stable
    change_pct: float = 0.0
    severity: str = "info"  # critical, warning, success, info
    category: str = ""
    source: str = ""


@dataclass
class DashboardSection:
    title: str
    cards: list[DashboardCard] = field(default_factory=list)
    order: int = 0


@dataclass
class Dashboard:
    id: str
    name: str
    description: str
    type: str  # executive, engineering, repository, architecture, security, ai, devops, tech_debt, developer, organization
    sections: list[DashboardSection] = field(default_factory=list)
    generated_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class DashboardEngine:
    """Generates structured dashboards from intelligence data across all categories."""

    DASHBOARD_TYPES = {
        "executive": "High-level KPIs for leadership and stakeholders",
        "engineering": "Engineering productivity and DORA metrics",
        "repository": "Repository health, growth, and composition",
        "architecture": "Architecture quality, patterns, and violations",
        "security": "Security posture, vulnerabilities, and risks",
        "ai": "AI system performance and effectiveness",
        "devops": "Deployment readiness and CI/CD health",
        "tech_debt": "Technical debt tracking and remediation",
        "developer": "Individual developer productivity",
        "organization": "Cross-repository organizational insights",
    }

    def __init__(self, repo_path: str = ""):
        self.repo_path = Path(repo_path) if repo_path else Path()

    def generate(self, dashboard_type: str, data: Optional[dict] = None) -> Dashboard:
        if dashboard_type not in self.DASHBOARD_TYPES:
            dashboard_type = "executive"

        db = Dashboard(
            id=f"{dashboard_type}-{hash(str(self.repo_path))}",
            name=dashboard_type.replace("_", " ").title(),
            description=self.DASHBOARD_TYPES[dashboard_type],
            type=dashboard_type,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

        generator = getattr(self, f"_build_{dashboard_type}_dashboard", None)
        if generator:
            generator(db, data or {})

        return db

    def generate_all(self, data: Optional[dict] = None) -> list[Dashboard]:
        return [self.generate(dt, data) for dt in self.DASHBOARD_TYPES]

    def _build_executive_dashboard(self, db: Dashboard, data: dict):
        db.sections = [
            DashboardSection(title="Health Overview", order=1, cards=[
                DashboardCard(id="overall-health", title="Overall Repository Health",
                              value=data.get("overall_health", 85), unit="%",
                              trend="up" if data.get("overall_health", 85) > 70 else "down",
                              severity="success" if data.get("overall_health", 85) > 70 else "warning",
                              category="health", source="health_engine"),
                DashboardCard(id="tech-debt-ratio", title="Technical Debt Ratio",
                              value=data.get("tech_debt_ratio", 15), unit="%",
                              trend="down" if data.get("tech_debt_ratio", 15) < 20 else "up",
                              severity="warning" if data.get("tech_debt_ratio", 15) > 20 else "success",
                              category="debt", source="tech_debt_engine"),
                DashboardCard(id="security-score", title="Security Score",
                              value=data.get("security_score", 80), unit="%",
                              trend="stable", severity="success" if data.get("security_score", 80) > 70 else "critical",
                              category="security", source="security_intelligence"),
            ]),
            DashboardSection(title="Engineering Velocity", order=2, cards=[
                DashboardCard(id="dora-score", title="DORA Elite Score",
                              value=data.get("dora_elite_score", 60), unit="%",
                              trend="up", severity="info", category="engineering", source="engineering_analytics"),
                DashboardCard(id="deploy-frequency", title="Deployment Frequency",
                              value=data.get("deployment_frequency", "weekly"), trend="stable",
                              severity="info", category="engineering", source="engineering_analytics"),
                DashboardCard(id="lead-time", title="Lead Time",
                              value=data.get("lead_time", 4), unit="hours",
                              trend="down" if data.get("lead_time", 4) < 8 else "up",
                              severity="success" if data.get("lead_time", 4) < 8 else "warning",
                              category="engineering", source="engineering_analytics"),
            ]),
            DashboardSection(title="AI & Intelligence", order=3, cards=[
                DashboardCard(id="ai-acceptance", title="AI Suggestion Acceptance",
                              value=data.get("ai_acceptance_rate", 65), unit="%",
                              trend="up", severity="success", category="ai", source="engineering_analytics"),
                DashboardCard(id="ai-readiness", title="AI Readiness Score",
                              value=data.get("ai_readiness", 50), unit="%",
                              trend="stable", severity="info", category="ai", source="health_engine"),
            ]),
        ]

    def _build_engineering_dashboard(self, db: Dashboard, data: dict):
        db.sections = [
            DashboardSection(title="DORA Metrics", order=1, cards=[
                DashboardCard(id="deploy-freq", title="Deployment Frequency",
                              value=data.get("deployment_frequency", "N/A"),
                              trend="stable", category="dora", source="engineering_analytics"),
                DashboardCard(id="lead-time-days", title="Lead Time for Changes",
                              value=data.get("lead_time", 0), unit="hours",
                              trend="stable", category="dora", source="engineering_analytics"),
                DashboardCard(id="change-failure", title="Change Failure Rate",
                              value=data.get("change_failure_rate", 0), unit="%",
                              trend="down", severity="critical" if data.get("change_failure_rate", 0) > 15 else "success",
                              category="dora", source="engineering_analytics"),
                DashboardCard(id="mttr", title="MTTR",
                              value=data.get("mttr", 0), unit="hours",
                              trend="down", category="dora", source="engineering_analytics"),
            ]),
            DashboardSection(title="Productivity", order=2, cards=[
                DashboardCard(id="commits-week", title="Commits/Week",
                              value=data.get("commits_per_week", 0), unit="commits",
                              trend="stable", category="productivity", source="engineering_analytics"),
                DashboardCard(id="lines-week", title="Lines Changed/Week",
                              value=data.get("lines_per_week", 0), unit="lines",
                              trend="stable", category="productivity", source="engineering_analytics"),
                DashboardCard(id="files-week", title="Files Changed/Week",
                              value=data.get("files_per_week", 0), unit="files",
                              trend="stable", category="productivity", source="engineering_analytics"),
            ]),
        ]

    def _build_repository_dashboard(self, db: Dashboard, data: dict):
        db.sections = [
            DashboardSection(title="Composition", order=1, cards=[
                DashboardCard(id="file-count", title="Total Files",
                              value=data.get("file_count", 0), unit="files",
                              category="composition", source="health_engine"),
                DashboardCard(id="source-lines", title="Source Lines of Code",
                              value=data.get("total_lines", 0), unit="lines",
                              category="composition", source="health_engine"),
                DashboardCard(id="lang-count", title="Languages",
                              value=data.get("language_count", 1), unit="langs",
                              category="composition", source="repository_intelligence"),
            ]),
            DashboardSection(title="Quality", order=2, cards=[
                DashboardCard(id="complexity", title="Avg Cyclomatic Complexity",
                              value=data.get("avg_complexity", 3), unit="",
                              trend="stable", severity="success" if data.get("avg_complexity", 3) < 7 else "warning",
                              category="quality", source="code_quality"),
                DashboardCard(id="maintainability", title="Maintainability Index",
                              value=data.get("maintainability_index", 70), unit="%",
                              trend="stable", severity="success" if data.get("maintainability_index", 70) > 60 else "warning",
                              category="quality", source="code_quality"),
                DashboardCard(id="coverage", title="Test Coverage",
                              value=data.get("coverage_pct", 0), unit="%",
                              trend="up", severity="success" if data.get("coverage_pct", 0) > 60 else "warning",
                              category="quality", source="test_intelligence"),
            ]),
        ]

    def _build_architecture_dashboard(self, db: Dashboard, data: dict):
        db.sections = [
            DashboardSection(title="Architecture Overview", order=1, cards=[
                DashboardCard(id="arch-score", title="Architecture Score",
                              value=data.get("architecture_score", 70), unit="%",
                              trend="stable", severity="info", category="architecture", source="health_engine"),
                DashboardCard(id="layer-count", title="Detected Layers",
                              value=data.get("layer_count", 0), unit="layers",
                              category="architecture", source="architecture_intelligence"),
                DashboardCard(id="pattern-count", title="Architecture Patterns",
                              value=data.get("pattern_count", 0), unit="patterns",
                              category="architecture", source="architecture_intelligence"),
            ]),
            DashboardSection(title="Violations", order=2, cards=[
                DashboardCard(id="layer-violations", title="Layer Violations",
                              value=data.get("layer_violations", 0), unit="violations",
                              severity="critical" if data.get("layer_violations", 0) > 0 else "success",
                              category="architecture", source="tech_debt_engine"),
                DashboardCard(id="dependency-cycles", title="Dependency Cycles",
                              value=data.get("dependency_cycles", 0), unit="cycles",
                              severity="critical" if data.get("dependency_cycles", 0) > 0 else "success",
                              category="architecture", source="architecture_intelligence"),
            ]),
        ]

    def _build_security_dashboard(self, db: Dashboard, data: dict):
        db.sections = [
            DashboardSection(title="Security Posture", order=1, cards=[
                DashboardCard(id="sec-score", title="Security Score",
                              value=data.get("security_score", 80), unit="%",
                              trend="stable", severity="success" if data.get("security_score", 80) > 70 else "critical",
                              category="security", source="security_intelligence"),
                DashboardCard(id="secrets-found", title="Secrets Exposed",
                              value=data.get("secrets_found", 0), unit="secrets",
                              severity="critical" if data.get("secrets_found", 0) > 0 else "success",
                              category="security", source="security_intelligence"),
                DashboardCard(id="vulnerabilities", title="Known CVEs",
                              value=data.get("vulnerabilities_found", 0), unit="CVEs",
                              severity="critical" if data.get("vulnerabilities_found", 0) > 0 else "success",
                              category="security", source="security_intelligence"),
            ]),
            DashboardSection(title="Risks", order=2, cards=[
                DashboardCard(id="critical-issues", title="Critical Issues",
                              value=data.get("critical_count", 0), unit="issues",
                              severity="critical" if data.get("critical_count", 0) > 0 else "success",
                              category="security", source="security_intelligence"),
                DashboardCard(id="high-issues", title="High Severity Issues",
                              value=data.get("high_count", 0), unit="issues",
                              severity="warning" if data.get("high_count", 0) > 0 else "success",
                              category="security", source="security_intelligence"),
            ]),
        ]

    def _build_ai_dashboard(self, db: Dashboard, data: dict):
        db.sections = [
            DashboardSection(title="AI Performance", order=1, cards=[
                DashboardCard(id="ai-latency-embed", title="Embedding Latency",
                              value=data.get("ai_embedding_ms", 0), unit="ms",
                              trend="down", severity="info", category="ai", source="performance_intelligence"),
                DashboardCard(id="ai-latency-search", title="Search Latency",
                              value=data.get("ai_search_ms", 0), unit="ms",
                              trend="down", severity="info", category="ai", source="performance_intelligence"),
                DashboardCard(id="ai-latency-completion", title="Completion Latency",
                              value=data.get("ai_completion_ms", 0), unit="ms",
                              trend="down", severity="info", category="ai", source="performance_intelligence"),
            ]),
            DashboardSection(title="AI Effectiveness", order=2, cards=[
                DashboardCard(id="acceptance-rate", title="Acceptance Rate",
                              value=data.get("ai_acceptance_rate", 0), unit="%",
                              trend="up", severity="success", category="ai", source="engineering_analytics"),
                DashboardCard(id="search-accuracy", title="Search Accuracy",
                              value=data.get("search_accuracy", 0), unit="%",
                              trend="up", severity="success", category="ai", source="engineering_analytics"),
                DashboardCard(id="token-usage", title="Avg Token Usage",
                              value=data.get("avg_token_usage", 0), unit="tokens",
                              trend="stable", category="ai", source="engineering_analytics"),
            ]),
        ]

    def _build_devops_dashboard(self, db: Dashboard, data: dict):
        db.sections = [
            DashboardSection(title="Deployment Readiness", order=1, cards=[
                DashboardCard(id="deploy-readiness", title="Deployment Readiness",
                              value=data.get("deployment_readiness", 50), unit="%",
                              trend="up", severity="success" if data.get("deployment_readiness", 50) > 70 else "warning",
                              category="devops", source="health_engine"),
                DashboardCard(id="docker-enabled", title="Docker Support",
                              value="Yes" if data.get("has_docker") else "No",
                              severity="success" if data.get("has_docker") else "warning",
                              category="devops", source="repository_intelligence"),
                DashboardCard(id="ci-cd", title="CI/CD Pipeline",
                              value=data.get("ci_cd", "None"),
                              severity="success" if data.get("ci_cd") else "warning",
                              category="devops", source="repository_intelligence"),
            ]),
        ]

    def _build_tech_debt_dashboard(self, db: Dashboard, data: dict):
        db.sections = [
            DashboardSection(title="Debt Overview", order=1, cards=[
                DashboardCard(id="debt-ratio", title="Technical Debt Ratio",
                              value=data.get("tech_debt_ratio", 0), unit="%",
                              trend="down", severity="warning" if data.get("tech_debt_ratio", 0) > 20 else "success",
                              category="tech_debt", source="tech_debt_engine"),
                DashboardCard(id="debt-effort", title="Estimated Effort to Fix",
                              value=data.get("total_effort_hours", 0), unit="hours",
                              category="tech_debt", source="tech_debt_engine"),
                DashboardCard(id="debt-items", title="Total Debt Items",
                              value=data.get("total_debt_items", 0), unit="items",
                              trend="stable", category="tech_debt", source="tech_debt_engine"),
            ]),
            DashboardSection(title="Breakdown", order=2, cards=[
                DashboardCard(id="critical-debt", title="Critical Items",
                              value=data.get("critical_debt", 0), unit="items",
                              severity="critical", category="tech_debt", source="tech_debt_engine"),
                DashboardCard(id="high-debt", title="High Items",
                              value=data.get("high_debt", 0), unit="items",
                              severity="warning", category="tech_debt", source="tech_debt_engine"),
                DashboardCard(id="medium-debt", title="Medium Items",
                              value=data.get("medium_debt", 0), unit="items",
                              severity="info", category="tech_debt", source="tech_debt_engine"),
            ]),
        ]

    def _build_developer_dashboard(self, db: Dashboard, data: dict):
        db.sections = [
            DashboardSection(title="Developer Impact", order=1, cards=[
                DashboardCard(id="commits", title="Commits (30d)",
                              value=data.get("developer_commits", 0), unit="commits",
                              category="developer", source="engineering_analytics"),
                DashboardCard(id="lines-changed", title="Lines Changed (30d)",
                              value=data.get("developer_lines", 0), unit="lines",
                              category="developer", source="engineering_analytics"),
                DashboardCard(id="prs-created", title="PRs Created (30d)",
                              value=data.get("developer_prs", 0), unit="PRs",
                              category="developer", source="engineering_analytics"),
            ]),
        ]

    def _build_organization_dashboard(self, db: Dashboard, data: dict):
        db.sections = [
            DashboardSection(title="Organization Overview", order=1, cards=[
                DashboardCard(id="repo-count", title="Repositories",
                              value=data.get("repository_count", 1), unit="repos",
                              category="organization"),
                DashboardCard(id="total-health", title="Avg Health Across Repos",
                              value=data.get("avg_org_health", 75), unit="%",
                              trend="stable", severity="info", category="organization"),
                DashboardCard(id="total-debt", title="Total Tech Debt",
                              value=data.get("total_org_debt_hours", 0), unit="hours",
                              category="organization"),
            ]),
        ]

    def to_json(self, dashboard: Dashboard) -> dict:
        return {
            "id": dashboard.id,
            "name": dashboard.name,
            "description": dashboard.description,
            "type": dashboard.type,
            "generated_at": dashboard.generated_at,
            "sections": [
                {
                    "title": s.title,
                    "order": s.order,
                    "cards": [c.__dict__ for c in s.cards],
                }
                for s in dashboard.sections
            ],
        }
