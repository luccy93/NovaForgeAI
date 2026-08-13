"""Browser automation (Volume 33).

Browser steps (click, fill, navigate, screenshot) are high-risk: they are
never executed without approval and never on the host browser. A remote
browser backend may be attached; otherwise the tool reports honest
unavailability.
"""
import logging
from typing import Any, Optional

from .tools import Tool, ToolError, ToolSpec

logger = logging.getLogger(__name__)


class RemoteBrowser:
    """Interface to an external browser runtime (absent by default)."""

    def navigate(self, url: str) -> dict:
        raise NotImplementedError

    def click(self, selector: str) -> dict:
        raise NotImplementedError

    def fill(self, selector: str, value: str) -> dict:
        raise NotImplementedError

    def screenshot(self) -> dict:
        raise NotImplementedError


class BrowserAgent:
    def __init__(self, remote: Optional[RemoteBrowser] = None,
                 guard=None):
        self.remote = remote
        self.guard = guard

    @property
    def available(self) -> bool:
        return self.remote is not None

    def perform(self, action: str, **kwargs) -> dict:
        if self.remote is None:
            return {"executed": False, "action": action,
                    "available": False,
                    "error": "no remote browser backend configured"}
        allowed = {"navigate", "click", "fill", "screenshot", "wait"}
        if action not in allowed:
            return {"executed": False, "action": action,
                    "available": True,
                    "error": f"unsupported action '{action}'"}
        if action == "navigate":
            url = kwargs.get("url", "")
            if self.guard is not None and not self.guard.validate_url(url):
                return {"executed": False, "action": action,
                        "available": True, "error": "URL rejected by SSRF guard"}
            return self.remote.navigate(url)
        try:
            result = getattr(self.remote, action)(**kwargs)
            if not isinstance(result, dict):
                result = {"result": result}
            result.setdefault("executed", True)
            return result
        except Exception as exc:
            return {"executed": False, "action": action,
                    "available": True,
                    "error": f"{type(exc).__name__}: {exc}"}

    def make_tool(self) -> Tool:
        return BrowserTool(self)


class BrowserTool(Tool):
    spec = ToolSpec("browser", "Browser", "Remote browser automation",
                    input_schema={"action": "string", "selector": "string"},
                    permissions=["interact"],
                    risk_level="high", timeout_s=60,
                    supported_environments=["sandboxed"],
                    approval_required=True)

    def __init__(self, agent: BrowserAgent):
        self._agent = agent

    def execute(self, inputs: dict, context: Optional[dict] = None) -> dict:
        action = inputs.get("action", "")
        if not action:
            raise ToolError("action required (navigate|click|fill|screenshot)")
        return self._agent.perform(action, **{
            k: v for k, v in inputs.items() if k not in ("action",)})