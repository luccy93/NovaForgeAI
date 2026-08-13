"""AI workflow generation (Volume 33).

AI-generated workflows go through the same pipeline as hand-written ones:
DSL parse -> DAG validation -> policy dry run -> approval -> execution.
Secrets are never exposed to the model; the generator only receives
schema/description text. Generated plans are marked `generated_by: ai`
and must pass a dry run before the gateway accepts them.
"""
import logging
from typing import Any, Callable, Optional

from .dsl import parse_workflow, WorkflowValidator
from .dryrun import validate_before_run
from .workflow import WorkflowSpec

logger = logging.getLogger(__name__)

GENERATOR_HINTS = """
Build a workflow definition with:
- name, trigger (type manual|schedule|webhook|event|github|gitlab)
- steps with id, type (task|tool|terminal|browser|infra|cicd|report|artifact|subworkflow|decision),
  action, inputs, depends_on, risk (low|medium|high), needs_approval for high-risk
- never include credentials, tokens or secrets
- keep actions to known automation actions: test, lint, build, deploy, checkout,
  notify, diagnose, scan_deps, scan_secrets, extract, transform, publish,
  verify, snapshot, regression, generate_report
"""


class WorkflowGenerator:
    """Honest AI-step support: when no LLM callback is attached, generation
    fails cleanly instead of hallucinating a plan."""

    def __init__(self, llm: Optional[Callable[[str], str]] = None,
                 policy=None):
        self.llm = llm
        self.policy = policy

    @property
    def available(self) -> bool:
        return self.llm is not None

    def generate(self, prompt: str, organization_id: str = "",
                 workflow_id: str = "") -> dict:
        if self.llm is None:
            return {"generated": False, "available": False,
                    "error": "no LLM callback attached; AI generation "
                             "unavailable",
                    "hints": GENERATOR_HINTS}
        try:
            text = self.llm(prompt + GENERATOR_HINTS)
        except Exception as exc:
            return {"generated": False, "available": True,
                    "error": f"{type(exc).__name__}: {exc}"}
        spec = parse_workflow({"workflow": {"name": "ai_generated",
                                            "trigger": {"type": "manual"}}},
                              organization_id=organization_id,
                              workflow_id=workflow_id or "ai_workflow")
        try:
            raw = _extract_workflow_dict(text)
            spec = parse_workflow(raw, organization_id=organization_id,
                                  workflow_id=workflow_id or
                                  spec.workflow_id)
        except Exception as exc:
            return {"generated": False, "available": True,
                    "raw": text,
                    "error": f"could not parse generated workflow: {exc}"}
        dry = validate_before_run(spec, self.policy, organization_id)
        return {"generated": True, "available": True,
                "workflow": spec, "dry_run": dry,
                "generated_by": "ai",
                "accepted": dry.get("verdict") == "approved_for_dry_run"}


def _extract_workflow_dict(text: str) -> dict:
    """Try JSON with a 'workflow' key; fall back to parsing a bare dict."""
    import json
    text = text.strip()
    try:
        data = json.loads(text)
    except Exception:
        for start, end in ((text.find("{"), text.rfind("}")),):
            if start == -1 or end <= start:
                raise ValueError("no JSON object found")
            try:
                data = json.loads(text[start:end + 1])
            except Exception as exc:
                raise ValueError(f"invalid JSON: {exc}")
    if "workflow" in data and isinstance(data["workflow"], dict):
        return data
    if set(data) <= {"name", "description", "trigger", "steps",
                     "policies", "created_by"}:
        return {"workflow": data}
    raise ValueError("workflow definition must have a 'steps' list")