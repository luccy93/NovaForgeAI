"""All 20 NovaForge AI agents — registered for auto-discovery."""

from app.agents.base import BaseAgent
from app.agents.schemas import AgentConfig, AgentRole, RetryPolicy
from app.agents.agents.planner import PlannerAgent
from app.agents.agents.repository import RepositoryIntelligenceAgent
from app.agents.agents.architect import ArchitectureAgent
from app.agents.agents.code_review import CodeReviewAgent
from app.agents.agents.refactoring import RefactoringAgent
from app.agents.agents.documentation import DocumentationAgent
from app.agents.agents.testing import TestingAgent
from app.agents.agents.security import SecurityAgent
from app.agents.agents.devops import DevOpsAgent
from app.agents.agents.deployment import DeploymentAgent
from app.agents.agents.analytics import AnalyticsAgent
from app.agents.agents.performance import PerformanceAgent
from app.agents.agents.database import DatabaseAgent
from app.agents.agents.api_agent import APIAgent
from app.agents.agents.frontend import FrontendAgent
from app.agents.agents.backend import BackendAgent
from app.agents.agents.bug_investigation import BugInvestigationAgent
from app.agents.agents.release_manager import ReleaseManagerAgent
from app.agents.agents.compliance import ComplianceAgent
from app.agents.agents.research import ResearchAgent


BASE_RETRY = RetryPolicy(max_retries=3, backoff_base=2.0, max_delay=60.0)

ALL_AGENTS: list[tuple[type[BaseAgent], AgentConfig]] = [
    (PlannerAgent, AgentConfig(
        name="planner", role=AgentRole.planner, version="1.0.0",
        description="Generates implementation plans with task breakdown, dependencies, and estimates",
        goals=["Break down complex tasks into actionable steps", "Identify dependencies between tasks",
               "Provide time estimates for each step", "Generate clear implementation order"],
        model="gpt-4o", temperature=0.3, retry_policy=BASE_RETRY,
        permissions=["read", "search_code", "list_files", "dependency_graph"],
    )),
    (RepositoryIntelligenceAgent, AgentConfig(
        name="repository_intelligence", role=AgentRole.repository_intelligence, version="1.0.0",
        description="Analyzes repository structure, history, and patterns to provide deep codebase understanding",
        goals=["Map repository structure and architecture", "Analyze commit history for patterns",
               "Identify code ownership and contribution patterns", "Track technology stack evolution"],
        model="gpt-4o", temperature=0.2, retry_policy=BASE_RETRY,
        permissions=["read", "search_code", "read_file", "git_history", "list_files", "dependency_graph"],
    )),
    (ArchitectureAgent, AgentConfig(
        name="architect", role=AgentRole.architect, version="1.0.0",
        description="Analyzes and designs software architecture, detects patterns and anti-patterns",
        goals=["Analyze system architecture from code", "Detect architectural anti-patterns",
               "Suggest architecture improvements", "Document architectural decisions"],
        model="gpt-4o", temperature=0.2, retry_policy=BASE_RETRY,
        permissions=["read", "search_code", "read_file", "dependency_graph", "list_files"],
    )),
    (CodeReviewAgent, AgentConfig(
        name="code_reviewer", role=AgentRole.code_reviewer, version="1.0.0",
        description="Reviews code for bugs, style issues, security vulnerabilities, and best practices",
        goals=["Find bugs and logic errors", "Enforce coding standards", "Detect security vulnerabilities",
               "Suggest performance improvements", "Check test coverage"],
        model="gpt-4o", temperature=0.1, retry_policy=BASE_RETRY,
        permissions=["read", "search_code", "read_file", "dependency_graph", "git_history"],
    )),
    (RefactoringAgent, AgentConfig(
        name="refactorer", role=AgentRole.refactorer, version="1.0.0",
        description="Identifies code smells and suggests refactoring opportunities with migration plans",
        goals=["Detect code smells and duplication", "Suggest refactoring strategies",
               "Generate migration-compatible code", "Improve code maintainability"],
        model="gpt-4o", temperature=0.3, retry_policy=BASE_RETRY,
        permissions=["read", "write", "search_code", "read_file", "dependency_graph"],
        require_human_approval=True,
    )),
    (DocumentationAgent, AgentConfig(
        name="documenter", role=AgentRole.documenter, version="1.0.0",
        description="Generates comprehensive documentation from code analysis",
        goals=["Generate docstrings and inline comments", "Create README and API docs",
               "Document architecture decisions", "Keep docs in sync with code"],
        model="gpt-4o", temperature=0.3, retry_policy=BASE_RETRY,
        permissions=["read", "search_code", "read_file", "list_files"],
    )),
    (TestingAgent, AgentConfig(
        name="tester", role=AgentRole.tester, version="1.0.0",
        description="Generates unit, integration, and E2E tests with coverage analysis",
        goals=["Generate unit tests for all functions", "Create integration test scenarios",
               "Achieve high code coverage", "Test edge cases and error paths"],
        model="gpt-4o", temperature=0.2, retry_policy=BASE_RETRY,
        permissions=["read", "search_code", "read_file", "dependency_graph", "list_files"],
    )),
    (SecurityAgent, AgentConfig(
        name="security", role=AgentRole.security, version="1.0.0",
        description="Performs security auditing — OWASP Top 10, dependency scanning, secret detection",
        goals=["Detect OWASP Top 10 vulnerabilities", "Scan dependencies for known CVEs",
               "Detect hardcoded secrets", "Audit authentication and authorization"],
        model="gpt-4o", temperature=0.1, retry_policy=BASE_RETRY,
        permissions=["read", "search_code", "read_file", "dependency_graph", "git_history"],
    )),
    (DevOpsAgent, AgentConfig(
        name="devops", role=AgentRole.devops, version="1.0.0",
        description="Manages CI/CD pipelines, infrastructure, Docker, and Kubernetes configuration",
        goals=["Review CI/CD pipeline configurations", "Optimize Dockerfiles and compose files",
               "Audit Kubernetes manifests", "Suggest infrastructure improvements"],
        model="gpt-4o", temperature=0.2, retry_policy=BASE_RETRY,
        permissions=["read", "write", "search_code", "read_file", "list_files"],
        require_human_approval=True,
    )),
    (DeploymentAgent, AgentConfig(
        name="deployment", role=AgentRole.deployment, version="1.0.0",
        description="Plans and validates deployments with rollback strategies and health checks",
        goals=["Plan deployment strategies", "Validate deployment readiness",
               "Generate rollback procedures", "Monitor deployment health"],
        model="gpt-4o", temperature=0.2, retry_policy=BASE_RETRY,
        permissions=["read", "write", "search_code", "read_file", "list_files"],
        require_human_approval=True,
    )),
    (AnalyticsAgent, AgentConfig(
        name="analytics", role=AgentRole.analytics, version="1.0.0",
        description="Analyzes usage data, generates insights, and creates analytics dashboards",
        goals=["Analyze application usage patterns", "Generate business intelligence reports",
               "Track key performance indicators", "Identify trends and anomalies"],
        model="gpt-4o", temperature=0.3, retry_policy=BASE_RETRY,
        permissions=["read", "search_code", "read_file"],
    )),
    (PerformanceAgent, AgentConfig(
        name="performance", role=AgentRole.performance, version="1.0.0",
        description="Profiles and optimizes application performance — queries, caching, bottlenecks",
        goals=["Identify performance bottlenecks", "Optimize database queries",
               "Suggest caching strategies", "Profile API response times"],
        model="gpt-4o", temperature=0.2, retry_policy=BASE_RETRY,
        permissions=["read", "search_code", "read_file", "dependency_graph"],
    )),
    (DatabaseAgent, AgentConfig(
        name="database", role=AgentRole.database, version="1.0.0",
        description="Analyzes and optimizes database schemas, queries, and migrations",
        goals=["Review database schema design", "Optimize SQL queries",
               "Plan database migrations", "Suggest indexing strategies"],
        model="gpt-4o", temperature=0.2, retry_policy=BASE_RETRY,
        permissions=["read", "write", "search_code", "read_file", "dependency_graph"],
        require_human_approval=True,
    )),
    (APIAgent, AgentConfig(
        name="api_agent", role=AgentRole.api_agent, version="1.0.0",
        description="Designs, reviews, and documents RESTful and GraphQL APIs",
        goals=["Review API design and consistency", "Generate API documentation",
               "Detect breaking changes", "Suggest endpoint improvements"],
        model="gpt-4o", temperature=0.2, retry_policy=BASE_RETRY,
        permissions=["read", "search_code", "read_file", "list_files"],
    )),
    (FrontendAgent, AgentConfig(
        name="frontend", role=AgentRole.frontend, version="1.0.0",
        description="Analyzes and optimizes frontend code, UI components, and state management",
        goals=["Review UI component architecture", "Optimize frontend performance",
               "Check accessibility compliance", "Suggest state management improvements"],
        model="gpt-4o", temperature=0.2, retry_policy=BASE_RETRY,
        permissions=["read", "search_code", "read_file", "list_files"],
    )),
    (BackendAgent, AgentConfig(
        name="backend", role=AgentRole.backend, version="1.0.0",
        description="Analyzes backend services, API endpoints, data flow, and business logic",
        goals=["Review backend service architecture", "Analyze API endpoint design",
               "Check data flow and validation", "Suggest backend improvements"],
        model="gpt-4o", temperature=0.2, retry_policy=BASE_RETRY,
        permissions=["read", "search_code", "read_file", "dependency_graph", "list_files"],
    )),
    (BugInvestigationAgent, AgentConfig(
        name="bug_investigator", role=AgentRole.bug_investigator, version="1.0.0",
        description="Investigates and localizes bugs using stack traces, logs, and code analysis",
        goals=["Analyze error reports and stack traces", "Localize bug to specific code",
               "Identify root causes", "Suggest fixes with evidence"],
        model="gpt-4o", temperature=0.1, retry_policy=RetryPolicy(max_retries=5, backoff_base=2.0, max_delay=60.0),
        permissions=["read", "search_code", "read_file", "dependency_graph", "git_history"],
    )),
    (ReleaseManagerAgent, AgentConfig(
        name="release_manager", role=AgentRole.release_manager, version="1.0.0",
        description="Manages release lifecycle — versioning, changelogs, readiness checks",
        goals=["Plan release versions and timelines", "Generate changelogs",
               "Assess release readiness", "Coordinate release tasks"],
        model="gpt-4o", temperature=0.3, retry_policy=BASE_RETRY,
        permissions=["read", "write", "search_code", "read_file", "git_history", "list_files"],
        require_human_approval=True,
    )),
    (ComplianceAgent, AgentConfig(
        name="compliance", role=AgentRole.compliance, version="1.0.0",
        description="Audits code for regulatory compliance — GDPR, SOC2, HIPAA, licensing",
        goals=["Check GDPR data handling compliance", "Audit SOC2 control requirements",
               "Review HIPAA compliance in health data", "Verify software license compliance"],
        model="gpt-4o", temperature=0.1, retry_policy=BASE_RETRY,
        permissions=["read", "search_code", "read_file", "dependency_graph", "list_files"],
    )),
    (ResearchAgent, AgentConfig(
        name="researcher", role=AgentRole.researcher, version="1.0.0",
        description="Researches technologies, libraries, patterns, and best practices",
        goals=["Research suitable libraries and frameworks", "Investigate best practices",
               "Compare technology options", "Provide evidence-based recommendations"],
        model="gpt-4o", temperature=0.4, retry_policy=BASE_RETRY,
        permissions=["read", "web_search", "doc_search", "search_code"],
    )),
]
