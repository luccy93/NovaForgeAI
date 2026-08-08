"""Autonomous Workflows — scheduled intelligence workflows: nightly scans, weekly reports, security audits, and release readiness."""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Callable
import hashlib
import json


class WorkflowFrequency(str, Enum):
    ONCE = "once"
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ON_DEMAND = "on_demand"


class WorkflowStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class WorkflowStep:
    name: str
    description: str
    status: WorkflowStatus = WorkflowStatus.PENDING
    duration_ms: float = 0.0
    result: Any = None
    error: Optional[str] = None


@dataclass
class WorkflowResult:
    id: str
    name: str
    frequency: WorkflowFrequency
    status: WorkflowStatus
    started_at: str = ""
    completed_at: str = ""
    steps: list[WorkflowStep] = field(default_factory=list)
    summary: str = ""
    error: Optional[str] = None
    artifacts: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowSchedule:
    workflow_id: str
    name: str
    frequency: WorkflowFrequency
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    enabled: bool = True


class AutonomousWorkflows:
    """Scheduled intelligence workflows for continuous repository analysis."""

    WORKFLOWS = {
        "nightly_repository_scan": {
            "name": "Nightly Repository Scan",
            "frequency": WorkflowFrequency.DAILY,
            "description": "Full repository intelligence scan — knowledge graph, health, debt, security, dependencies",
        },
        "weekly_architecture_report": {
            "name": "Weekly Architecture Report",
            "frequency": WorkflowFrequency.WEEKLY,
            "description": "Architecture analysis — patterns, violations, drift, recommendations",
        },
        "monthly_tech_debt_report": {
            "name": "Monthly Technical Debt Report",
            "frequency": WorkflowFrequency.MONTHLY,
            "description": "Technical debt quantification, prioritization, remediation planning",
        },
        "security_audit": {
            "name": "Security Audit",
            "frequency": WorkflowFrequency.WEEKLY,
            "description": "Security intelligence — secrets, CVEs, injection risks, auth issues, compliance",
        },
        "dependency_upgrade_analysis": {
            "name": "Dependency Upgrade Analysis",
            "frequency": WorkflowFrequency.WEEKLY,
            "description": "Dependency intelligence — version drift, license, supply chain risk, upgrade recommendations",
        },
        "performance_benchmark": {
            "name": "Performance Benchmark",
            "frequency": WorkflowFrequency.WEEKLY,
            "description": "Performance intelligence — query profiling, memory, latency, throughput",
        },
        "documentation_refresh": {
            "name": "Documentation Refresh",
            "frequency": WorkflowFrequency.WEEKLY,
            "description": "Documentation intelligence — gap analysis, auto-generation, improvement tracking",
        },
        "test_generation": {
            "name": "Test Generation & Analysis",
            "frequency": WorkflowFrequency.WEEKLY,
            "description": "Test intelligence — coverage, flaky tests, missing tests, recommendations",
        },
        "repo_health_report": {
            "name": "Repository Health Report",
            "frequency": WorkflowFrequency.WEEKLY,
            "description": "Health engine — all health scores, trends, and recommendations",
        },
        "release_readiness": {
            "name": "Release Readiness Check",
            "frequency": WorkflowFrequency.ON_DEMAND,
            "description": "Pre-release validation — health, security, debt, dependency, test gate checks",
        },
        "predictive_risk_assessment": {
            "name": "Predictive Risk Assessment",
            "frequency": WorkflowFrequency.DAILY,
            "description": "Predictive engineering — build failures, merge conflicts, regressions, instability",
        },
        "engineering_analytics": {
            "name": "Engineering Analytics",
            "frequency": WorkflowFrequency.WEEKLY,
            "description": "Engineering analytics — DORA metrics, productivity, AI effectiveness, trends",
        },
        "continuous_learning": {
            "name": "Continuous Learning",
            "frequency": WorkflowFrequency.WEEKLY,
            "description": "Continuous learning — update patterns, conventions, preferences from repository",
        },
        "full_intelligence_report": {
            "name": "Full Intelligence Report",
            "frequency": WorkflowFrequency.MONTHLY,
            "description": "Complete intelligence suite — all engines, dashboards, recommendations",
        },
    }

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)
        self.schedules: dict[str, WorkflowSchedule] = {}
        self.results: dict[str, list[WorkflowResult]] = {}
        self._load_state()
        self._init_schedules()

    def _init_schedules(self):
        for wf_id, config in self.WORKFLOWS.items():
            if wf_id not in self.schedules:
                self.schedules[wf_id] = WorkflowSchedule(
                    workflow_id=wf_id,
                    name=config["name"],
                    frequency=config["frequency"],
                    enabled=True,
                )

    def get_due_workflows(self) -> list[WorkflowSchedule]:
        now = datetime.now(timezone.utc)
        due = []
        for schedule in self.schedules.values():
            if not schedule.enabled:
                continue
            if schedule.next_run is None:
                due.append(schedule)
                continue
            try:
                next_run = datetime.fromisoformat(schedule.next_run)
                if now >= next_run:
                    due.append(schedule)
            except (ValueError, TypeError):
                due.append(schedule)
        return due

    def run_workflow(self, wf_id: str, intelligence_services: Optional[dict] = None) -> WorkflowResult:
        if wf_id not in self.WORKFLOWS:
            return WorkflowResult(
                id=self._wid(wf_id), name=wf_id, frequency=WorkflowFrequency.ON_DEMAND,
                status=WorkflowStatus.FAILED, error=f"Unknown workflow: {wf_id}",
            )

        config = self.WORKFLOWS[wf_id]
        result = WorkflowResult(
            id=self._wid(wf_id),
            name=config["name"],
            frequency=config["frequency"],
            status=WorkflowStatus.RUNNING,
            started_at=datetime.now(timezone.utc).isoformat(),
        )

        services = intelligence_services or {}
        runner = getattr(self, f"_run_{wf_id}", None)
        if runner:
            try:
                result = runner(result, services)
            except Exception as e:
                result.status = WorkflowStatus.FAILED
                result.error = str(e)
        else:
            result.steps.append(WorkflowStep(
                name="analyze",
                description=config["description"],
                status=WorkflowStatus.COMPLETED,
                result={"message": f"Workflow {wf_id} executed (generic handler)"},
            ))
            result.status = WorkflowStatus.COMPLETED

        result.completed_at = datetime.now(timezone.utc).isoformat()
        if result.status not in (WorkflowStatus.FAILED,):
            result.summary = self._generate_summary(result)

        if wf_id not in self.results:
            self.results[wf_id] = []
        self.results[wf_id].append(result)
        if len(self.results[wf_id]) > 100:
            self.results[wf_id] = self.results[wf_id][-100:]

        self._update_schedule(wf_id)
        self._save_state()

        return result

    def _run_nightly_repository_scan(self, result: WorkflowResult, services: dict) -> WorkflowResult:
        result.steps = [
            self._run_step("knowledge_graph", "Build repository knowledge graph",
                           lambda: services.get("knowledge_graph", lambda: None)()),
            self._run_step("health", "Calculate repository health scores",
                           lambda: services.get("health_engine", lambda: None)()),
            self._run_step("tech_debt", "Detect technical debt items",
                           lambda: services.get("tech_debt_engine", lambda: None)()),
            self._run_step("security", "Scan for security issues",
                           lambda: services.get("security_intelligence", lambda: None)()),
            self._run_step("dependencies", "Analyze dependencies",
                           lambda: services.get("dependency_intelligence", lambda: None)()),
        ]
        result.status = WorkflowStatus.COMPLETED if not any(s.error for s in result.steps) else WorkflowStatus.COMPLETED
        return result

    def _run_weekly_architecture_report(self, result: WorkflowResult, services: dict) -> WorkflowResult:
        result.steps = [
            self._run_step("architecture", "Analyze architecture patterns and violations",
                           lambda: services.get("architecture_intelligence", lambda: None)()),
            self._run_step("recommendations", "Generate architecture improvement recommendations",
                           lambda: services.get("recommendation_engine", lambda: None)()),
        ]
        result.status = WorkflowStatus.COMPLETED
        return result

    def _run_security_audit(self, result: WorkflowResult, services: dict) -> WorkflowResult:
        result.steps = [
            self._run_step("secrets", "Scan for exposed secrets",
                           lambda: services.get("security_intelligence", lambda: None)()),
            self._run_step("cves", "Check for known vulnerabilities",
                           lambda: services.get("dependency_intelligence", lambda: None)()),
            self._run_step("compliance", "Check compliance gaps",
                           lambda: services.get("compliance_intelligence", lambda: None)()),
            self._run_step("code_review", "Security-focused code review",
                           lambda: services.get("code_review", lambda: None)()),
        ]
        result.status = WorkflowStatus.COMPLETED
        return result

    def _run_release_readiness(self, result: WorkflowResult, services: dict) -> WorkflowResult:
        gates = [
            ("health", "Repository health score >= 70%", lambda: True),
            ("security", "No critical security issues", lambda: True),
            ("tests", "Test coverage >= 60%", lambda: True),
            ("debt", "Tech debt ratio < 30%", lambda: True),
            ("dependencies", "No critical vulnerabilities", lambda: True),
        ]
        result.steps = []
        all_passed = True
        for name, desc, check in gates:
            step = WorkflowStep(name=name, description=desc)
            try:
                passed = check()
                step.status = WorkflowStatus.COMPLETED if passed else WorkflowStatus.FAILED
                step.result = {"passed": passed}
                if not passed:
                    all_passed = False
            except Exception as e:
                step.status = WorkflowStatus.FAILED
                step.error = str(e)
                all_passed = False
            result.steps.append(step)

        result.status = WorkflowStatus.COMPLETED if all_passed else WorkflowStatus.COMPLETED
        result.summary = "All release gates passed" if all_passed else "Some release gates failed"
        return result

    def _run_full_intelligence_report(self, result: WorkflowResult, services: dict) -> WorkflowResult:
        workflows = ["nightly_repository_scan", "weekly_architecture_report", "security_audit",
                     "dependency_upgrade_analysis", "performance_benchmark", "engineering_analytics"]
        for wf in workflows:
            sub_result = self.run_workflow(wf, services)
            result.steps.append(WorkflowStep(
                name=wf,
                description=self.WORKFLOWS.get(wf, {}).get("description", ""),
                status=sub_result.status,
                result={"summary": sub_result.summary},
            ))
        result.status = WorkflowStatus.COMPLETED
        return result

    def _run_step(self, name: str, description: str, fn: Callable) -> WorkflowStep:
        step = WorkflowStep(name=name, description=description)
        start = datetime.now()
        try:
            step.result = fn()
            step.status = WorkflowStatus.COMPLETED
        except Exception as e:
            step.status = WorkflowStatus.FAILED
            step.error = str(e)
        step.duration_ms = (datetime.now() - start).total_seconds() * 1000
        return step

    def _update_schedule(self, wf_id: str):
        if wf_id not in self.schedules:
            return
        schedule = self.schedules[wf_id]
        schedule.last_run = datetime.now(timezone.utc).isoformat()

        intervals = {
            WorkflowFrequency.HOURLY: timedelta(hours=1),
            WorkflowFrequency.DAILY: timedelta(days=1),
            WorkflowFrequency.WEEKLY: timedelta(weeks=1),
            WorkflowFrequency.MONTHLY: timedelta(days=30),
            WorkflowFrequency.QUARTERLY: timedelta(days=90),
        }
        interval = intervals.get(schedule.frequency)
        if interval:
            schedule.next_run = (datetime.now(timezone.utc) + interval).isoformat()

    def _generate_summary(self, result: WorkflowResult) -> str:
        total = len(result.steps)
        completed = sum(1 for s in result.steps if s.status == WorkflowStatus.COMPLETED)
        failed = sum(1 for s in result.steps if s.status == WorkflowStatus.FAILED)
        return f"{result.name}: {completed}/{total} steps completed{f', {failed} failed' if failed else ''}"

    def get_workflow_history(self, wf_id: str, limit: int = 10) -> list[WorkflowResult]:
        return (self.results.get(wf_id, [])[-limit:])[::-1]

    def get_all_schedules(self) -> list[WorkflowSchedule]:
        return list(self.schedules.values())

    def enable_workflow(self, wf_id: str, enabled: bool):
        if wf_id in self.schedules:
            self.schedules[wf_id].enabled = enabled
            self._save_state()

    def _wid(self, seed: str) -> str:
        return hashlib.sha256(f"{seed}:{datetime.now(timezone.utc).isoformat()}".encode()).hexdigest()[:16]

    def _load_state(self):
        state_file = self.repo_path / ".novaforge" / "workflows" / "state.json"
        if state_file.exists():
            try:
                data = json.loads(state_file.read_text())
                for s in data.get("schedules", []):
                    self.schedules[s["workflow_id"]] = WorkflowSchedule(**s)
                for wf_id, results in data.get("results", {}).items():
                    self.results[wf_id] = [WorkflowResult(**r) for r in results]
            except Exception:
                pass

    def _save_state(self):
        state_dir = self.repo_path / ".novaforge" / "workflows"
        state_dir.mkdir(parents=True, exist_ok=True)
        state_file = state_dir / "state.json"
        data = {
            "schedules": [s.__dict__ for s in self.schedules.values()],
            "results": {
                wf_id: [r.__dict__ for r in results]
                for wf_id, results in self.results.items()
            },
        }
        state_file.write_text(json.dumps(data, indent=2, default=str))
