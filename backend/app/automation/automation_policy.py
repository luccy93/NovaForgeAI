"""Automation policy enforcement (Volume 33).

Central gate for everything the engine does: risk classification, tool
allowlists, domain allowlists, protected actions, high-risk approval
requirements and tenant policies. The engine consults AutomationPolicy
before executing any step; it can never be bypassed by a workflow.
"""
import logging
from typing import Any, Optional

from .workflow import WorkflowSpec, WorkflowStep

logger = logging.getLogger(__name__)

HIGH_RISK_TOOLS = {"shell", "terminal", "browser_click", "deploy",
                   "infra_apply", "git_force_push", "db_write", "delete"}
PROTECTED_TOOLS = {"terminal", "browser", "infra", "deploy", "release",
                   "payment", "data_delete"}
DEFAULT_ALLOWED_DOMAINS = ("https://github.com", "https://api.github.com")


class AutomationPolicy:
    """Tenant-scoped policy. Unknown tenants fall back to defaults."""

    def __init__(self, config: Optional[dict] = None):
        self._config = config or {}

    def tenant_config(self, organization_id: str) -> dict:
        tenant = self._config.get(organization_id, {})
        return {**self._config.get("*", {}), **tenant}

    # ---------------------------------------------------------------
    def classify_risk(self, step: WorkflowStep,
                      organization_id: str = "") -> str:
        """Effective risk: explicit risk wins, except dangerous actions are
        ALWAYS escalated to high regardless of what the workflow declares."""
        if step.action in HIGH_RISK_TOOLS or step.type in (
                "terminal", "browser", "infra", "deploy", "cicd"):
            return "high"
        if step.risk in ("medium", "high"):
            return step.risk
        return "low"

    def requires_approval(self, step: WorkflowStep,
                          organization_id: str = "") -> bool:
        if step.needs_approval:
            return True
        cfg = self.tenant_config(organization_id)
        approve_high = cfg.get("approve_high_risk", True)
        if approve_high and self.classify_risk(step, organization_id) == "high":
            return True
        return step.action in cfg.get("approve_actions", [])

    def authorize(self, step: WorkflowStep, organization_id: str = "",
                  context: Optional[dict] = None) -> tuple[bool, str]:
        """Decision tuple (allowed, reason). Engine refuses execution when
        not allowed."""
        cfg = self.tenant_config(organization_id)
        if cfg.get("mode") == "lockdown":
            return False, "tenant policy is in lockdown mode"
        if step.action in cfg.get("deny_actions", []):
            return False, f"action '{step.action}' denied by policy"
        tool_allow = cfg.get("allowed_tools")
        if tool_allow and step.type == "tool" and \
                step.action not in tool_allow:
            return False, f"tool '{step.action}' not allowed"
        allowed_domains = cfg.get("allowed_domains",
                                  DEFAULT_ALLOWED_DOMAINS)
        url = (step.inputs or {}).get("url", "")
        if url and not any(url.startswith(d) for d in allowed_domains):
            return False, f"domain '{url}' not allowed"
        if step.type == "tool" and step.action in cfg.get(
                "approve_actions", []):
            return True, "approval required (checked by engine)"
        return True, "allowed"

    def can_trigger(self, organization_id: str, trigger_type: str) -> bool:
        cfg = self.tenant_config(organization_id)
        blocked = cfg.get("blocked_triggers", [])
        return trigger_type not in blocked

    def describe(self, organization_id: str = "") -> dict:
        cfg = self.tenant_config(organization_id)
        return {"mode": cfg.get("mode", "standard"),
                "approve_high_risk": cfg.get("approve_high_risk", True),
                "approve_actions": cfg.get("approve_actions", []),
                "deny_actions": cfg.get("deny_actions", []),
                "allowed_domains": cfg.get("allowed_domains",
                                           list(DEFAULT_ALLOWED_DOMAINS)),
                "blocked_triggers": cfg.get("blocked_triggers", [])}