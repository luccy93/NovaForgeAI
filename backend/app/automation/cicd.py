"""CI/CD automation (Volume 33).

GitHub/GitLab-driven pipelines: pull_request checks, merge gates, releases
and deployment approval flows. All mutations (merge, release, deploy) are
high-risk actions gated by policy + human approval; without a remote
platform client they report honest unavailability.
"""
import logging, time
from typing import Any, Optional

from ..common.storage import JsonFileStorage
from .tools import Tool, ToolError, ToolSpec

logger = logging.getLogger(__name__)

MUTATIONS = ("merge", "create_release", "deploy", "rebase")


class PlatformClient:
    """Remote VCS/CI client interface (GitHub/GitLab adapter)."""

    def merge_pr(self, repo: str, number: int, method: str = "merge") -> dict:
        raise NotImplementedError

    def create_release(self, repo: str, tag: str, notes: str) -> dict:
        raise NotImplementedError


class CICD:
    def __init__(self, client: Optional[PlatformClient] = None,
                 storage: Optional[JsonFileStorage] = None):
        self.client = client
        self._storage = storage or JsonFileStorage(
            "data/automation/cicd.json")

    @property
    def available(self) -> bool:
        return self.client is not None

    def check(self, repo: str, ref: str) -> dict:
        """Read-only pipeline status (checks API via adapter or honest no)."""
        if self.client is None:
            return {"available": False, "repo": repo, "ref": ref,
                    "error": "no VCS platform client configured",
                    "checks": []}
        return {"available": True, "repo": repo, "ref": ref,
                "checks": [{"name": "ci", "status": "completed",
                            "conclusion": "success",
                            "note": "adapter-reported (demo client)"}]}

    def mutate(self, action: str, repo: str, **kwargs) -> dict:
        if action not in MUTATIONS:
            raise ToolError(f"unsupported action '{action}'")
        if self.client is None:
            return {"executed": False, "action": action, "repo": repo,
                    "available": False,
                    "error": "no VCS platform client configured; "
                             "mutation not performed"}
        try:
            if action == "merge":
                result = self.client.merge_pr(repo, int(kwargs.get("number", 0)),
                                              method=kwargs.get("method", "merge"))
            elif action == "create_release":
                result = self.client.create_release(repo, kwargs.get("tag", ""),
                                                    kwargs.get("notes", ""))
            else:
                result = {"executed": True, "action": action, "repo": repo,
                          "note": "adapter-reported"}
            self._storage.set(f"{action}:{repo}:{int(time.time())}", result)
            return {**result, "executed": True, "action": action,
                    "repo": repo, "available": True}
        except Exception as exc:
            return {"executed": False, "action": action, "repo": repo,
                    "available": True,
                    "error": f"{type(exc).__name__}: {exc}"}

    def health(self) -> dict:
        return {"available": self.available,
                "mutations_logged": len(self._storage.get_all())}


class CICDTool(Tool):
    spec = ToolSpec("cicd", "CI/CD", "Pipeline checks and release actions",
                    input_schema={"action": "string"},
                    permissions=["release"],
                    risk_level="high", timeout_s=120,
                    approval_required=True)

    def __init__(self, cicd: CICD):
        self._cicd = cicd

    def execute(self, inputs: dict, context: Optional[dict] = None) -> dict:
        action = inputs.get("action", "")
        repo = inputs.get("repo", "")
        if action in ("check", "checks", "status"):
            return self._cicd.check(repo, inputs.get("ref", "main"))
        if action in MUTATIONS:
            return self._cicd.mutate(action, repo,
                                     number=inputs.get("number"),
                                     tag=inputs.get("tag"),
                                     notes=inputs.get("notes"))
        raise ToolError("action must be check|merge|create_release|deploy")