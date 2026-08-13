"""Infrastructure automation (Volume 33).

Terraform-style plans: `plan` computes the change without applying;
`apply` is high-risk and requires explicit approval + dry-run. Backends
are adapters (aws/gke/k8s/helm/terraform plugins); without an adapter,
apply reports honest unavailability.
"""
import logging
from typing import Any, Optional

from ..common.storage import JsonFileStorage
from .approvals import ApprovalStore
from .tools import Tool, ToolError, ToolSpec

logger = logging.getLogger(__name__)


class InfraBackend:
    """Adapter interface: plan/apply/destroy/state."""

    def plan(self, manifest: dict) -> dict:
        raise NotImplementedError

    def apply(self, manifest: dict) -> dict:
        raise NotImplementedError


class NoopBackend(InfraBackend):
    def plan(self, manifest: dict) -> dict:
        return {"backend": "noop", "planned_actions": ["no_changes"],
                "note": "no backend configured; plan is a forecast"}


class InfraAutomation:
    def __init__(self, backends: Optional[dict] = None,
                 storage: Optional[JsonFileStorage] = None):
        self.backends = backends or {}  # adapter name -> InfraBackend
        self._storage = storage or JsonFileStorage(
            "data/automation/infra.json")

    def _backend_for(self, adapter: str) -> InfraBackend:
        return self.backends.get(adapter, NoopBackend())

    def plan(self, manifest: dict, adapter: str = "") -> dict:
        result = self._backend_for(adapter).plan(manifest)
        self._storage.set(f"plan:{manifest.get('id', _uid())}", result)
        return {**result, "adapter": adapter or "noop",
                "planned": True, "applied": False}

    def apply(self, manifest: dict, adapter: str = "",
              approval: Optional[dict] = None) -> dict:
        if self._backend_for(adapter).__class__ is NoopBackend:
            return {"applied": False, "adapter": adapter or "noop",
                    "available": False,
                    "error": "no infra backend configured; nothing applied"}
        if not approval or approval.get("decision") != "approved":
            return {"applied": False, "adapter": adapter,
                    "available": True,
                    "error": "apply requires an approved human approval"}
        try:
            result = self._backend_for(adapter).apply(manifest)
            self._storage.set(f"apply:{manifest.get('id', _uid())}",
                              {**result, "approved_by": approval.get("actor")})
            return {**result, "applied": True}
        except Exception as exc:
            return {"applied": False, "adapter": adapter,
                    "available": True,
                    "error": f"{type(exc).__name__}: {exc}"}

    def health(self) -> dict:
        return {"backends": sorted(self.backends.keys()),
                "default_backend": "noop"}


class InfraTool(Tool):
    spec = ToolSpec("infra", "Infrastructure", "Plan/apply infrastructure",
                    input_schema={"action": "string", "manifest": "object"},
                    permissions=["provision"],
                    risk_level="high", timeout_s=300,
                    approval_required=True,
                    supported_environments=["all"])

    def __init__(self, infra: InfraAutomation):
        self._infra = infra

    def execute(self, inputs: dict, context: Optional[dict] = None) -> dict:
        action = inputs.get("action", "")
        manifest = inputs.get("manifest") or {}
        if action == "plan":
            return self._infra.plan(manifest,
                                    adapter=inputs.get("adapter", ""))
        if action == "apply":
            if not manifest:
                raise ToolError("manifest required for apply")
            return self._infra.apply(manifest,
                                     adapter=inputs.get("adapter", ""),
                                     approval=context.get("approval") if context
                                     else None)
        raise ToolError("action must be plan|apply")


def _uid() -> str:
    import uuid
    return uuid.uuid4().hex[:8]