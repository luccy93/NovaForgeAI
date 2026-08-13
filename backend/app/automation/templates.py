"""Workflow templates (Volume 33).

Curated, validated workflow blueprints (CI, deploy, incident, security,
data, test). Templates are the safe starting point for AI-generated
workflows: AI fills parameters, the gateway still dry-runs + validates.
"""
import logging
from typing import Any, Optional

from ..common.storage import JsonFileStorage
from .dag import validate_dag
from .dsl import parse_workflow

logger = logging.getLogger(__name__)


def _templates() -> dict:
    return {
        "ci_pipeline": {
            "name": "CI Pipeline",
            "description": "Pull-request CI: test, lint, build, report",
            "trigger": {"type": "pull_request"},
            "steps": [
                {"id": "checkout", "type": "task", "action": "checkout",
                 "risk": "low"},
                {"id": "unit_tests", "type": "task", "action": "test",
                 "depends_on": ["checkout"], "risk": "low"},
                {"id": "lint", "type": "task", "action": "lint",
                 "depends_on": ["checkout"], "risk": "low"},
                {"id": "build", "type": "task", "action": "build",
                 "depends_on": ["unit_tests"], "risk": "medium"},
                {"id": "report", "type": "report", "action": "generate_report",
                 "depends_on": ["build"], "risk": "low",
                 "inputs": {"title": "CI Report"}},
            ]},
        "deploy": {
            "name": "Deployment",
            "description": "Approved production deployment",
            "trigger": {"type": "manual"},
            "steps": [
                {"id": "tests", "type": "task", "action": "test",
                 "risk": "low"},
                {"id": "plan", "type": "infra", "action": "infra",
                 "depends_on": ["tests"], "risk": "medium",
                 "inputs": {"action": "plan"}},
                {"id": "apply", "type": "infra", "action": "infra",
                 "depends_on": ["plan"], "risk": "high",
                 "needs_approval": True,
                 "compensation": "rollback",
                 "inputs": {"action": "apply"}},
            ]},
        "incident_runbook": {
            "name": "Incident Runbook",
            "description": "Diagnose incidents, notify, collect evidence",
            "trigger": {"type": "incident"},
            "steps": [
                {"id": "collect", "type": "task", "action": "diagnose",
                 "risk": "low"},
                {"id": "notify", "type": "task", "action": "notify",
                 "depends_on": ["collect"], "risk": "low"},
                {"id": "evidence", "type": "artifact",
                 "depends_on": ["collect"], "risk": "low",
                 "action": "snapshot"},
            ]},
        "security_scan": {
            "name": "Security Scan",
            "description": "Dependency and secret scanning on commits",
            "trigger": {"type": "commit"},
            "steps": [
                {"id": "deps", "type": "security", "action": "scan_deps",
                 "risk": "low"},
                {"id": "secrets", "type": "security", "action": "scan_secrets",
                 "depends_on": ["deps"], "risk": "medium"},
                {"id": "report", "type": "report",
                 "depends_on": ["secrets"], "risk": "low",
                 "action": "generate_report"},
            ]},
        "data_pipeline": {
            "name": "Data Pipeline",
            "description": "Extract-transform-publish data job",
            "trigger": {"type": "schedule", "cron": "0 2 * * *"},
            "steps": [
                {"id": "extract", "type": "task", "action": "extract",
                 "risk": "low"},
                {"id": "transform", "type": "task", "action": "transform",
                 "depends_on": ["extract"], "risk": "low"},
                {"id": "publish", "type": "task", "action": "publish",
                 "depends_on": ["transform"], "risk": "medium"},
                {"id": "verify", "type": "task", "action": "verify",
                 "depends_on": ["publish"], "risk": "low"},
            ]},
        "test_automation": {
            "name": "Test Automation",
            "description": "Scheduled regression sweep",
            "trigger": {"type": "schedule", "cron": "0 * * * *"},
            "steps": [
                {"id": "snapshot", "type": "task", "action": "snapshot",
                 "risk": "low"},
                {"id": "regression", "type": "task", "action": "regression",
                 "depends_on": ["snapshot"], "risk": "low"},
                {"id": "report", "type": "report",
                 "depends_on": ["regression"], "risk": "low"},
            ]},
    }


class TemplateLibrary:
    def __init__(self, templates: Optional[dict] = None,
                 storage: Optional[JsonFileStorage] = None):
        self._templates = {**(_templates()), **(templates or {})}
        self._storage = storage  # optional persistence of custom templates

    def get(self, template_id: str) -> Optional[dict]:
        return self._templates.get(template_id)

    def list(self) -> list[dict]:
        return [{"template_id": tid, "name": t.get("name", tid),
                 "description": t.get("description", ""),
                 "steps": len(t.get("steps", []))}
                for tid, t in self._templates.items()]

    def instantiate(self, template_id: str, params: dict | None = None,
                    organization_id: str = "") -> dict | None:
        template = self.get(template_id)
        if template is None:
            return None
        params = params or {}
        steps = []
        for step in template.get("steps", []):
            step = dict(step)
            step["inputs"] = {**step.get("inputs", {}),
                              **params.get(step.get("id"), {})}
            if step.get("id") in params.get("_skip", []):
                continue
            step["depends_on"] = [params.get(d, d) for d in
                                  step.get("depends_on", [])]
            steps.append(step)
        spec = parse_workflow({"workflow": {
            "name": params.get("name", template["name"]),
            "description": template.get("description", ""),
            "trigger": params.get("trigger", template.get("trigger",
                                                          {"type": "manual"})),
            "steps": steps}}, organization_id=organization_id,
            workflow_id=params.get("workflow_id", ""))
        return {"workflow": spec_to_dict(spec), "template_id": template_id}


def spec_to_dict(spec) -> dict:
    from dataclasses import asdict
    return asdict(spec)