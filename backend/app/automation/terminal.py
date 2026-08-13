"""Terminal automation (Volume 33).

The terminal tool NEVER executes commands on the host: it reports honest
unavailability unless an explicit remote sandbox backend is configured.
With a backend, commands run outside the host and are subject to
risk classification + approval. Output sizes are capped.
"""
import logging
from typing import Any, Callable, Optional

from .tools import Tool, ToolError, ToolSpec

logger = logging.getLogger(__name__)

DANGEROUS_PATTERNS = [
    r"\brm\s+-rf\b", r"\bmkfs\b", r"\bdd\s+if=", r"\bchmod\s+777\b",
    r"\bcurl\b.*\|.*\bsh\b", r"\bwget\b.*\|.*\bsh\b", r"\bsudo\b",
    r"\bpasswd\b", r"\bshutdown\b", r"\breboot\b", r"\b>:\s*/dev/\w+\b",
]


class RiskEngine:
    """Static command classification (low/medium/high) via patterns + length."""

    def __init__(self):
        import re
        self._patterns = [re.compile(p) for p in DANGEROUS_PATTERNS]

    def classify(self, command: str) -> dict:
        for pattern in self._patterns:
            if pattern.search(command):
                return {"risk": "high",
                        "reason": f"matches dangerous pattern {pattern.pattern}"}
        if len(command) > 300:
            return {"risk": "medium", "reason": "long command"}
        if any(marker in command for marker in ("&&", "|", ";", ">")):
            return {"risk": "medium", "reason": "command chaining"}
        return {"risk": "low", "reason": "simple command"}


class RemoteRunner:
    """Interface for an external sandbox. Subclass and configure via
    the terminal backend; absent by default."""

    def execute(self, command: str, timeout_s: int) -> dict:
        raise NotImplementedError


class TerminalSandbox:
    """Honest terminal: with an explicit remote runner it executes remotely;
    otherwise it refuses with a clear reason. Approval is enforced by the
    gateway, not here."""

    def __init__(self, remote_runner: Optional[RemoteRunner] = None,
                 risk_engine: Optional[RiskEngine] = None,
                 max_output_bytes: int = 200_000):
        self.remote_runner = remote_runner
        self.risk_engine = risk_engine or RiskEngine()
        self.max_output_bytes = max_output_bytes

    @property
    def available(self) -> bool:
        return self.remote_runner is not None

    def execute(self, command: str, timeout_s: int = 30,
                cwd: str = "", env: Optional[dict] = None) -> dict:
        risk = self.risk_engine.classify(command)
        if self.remote_runner is None:
            return {"executed": False, "command": command,
                    "risk": risk["risk"], "reason": risk["reason"],
                    "available": False,
                    "error": "no sandbox backend configured; commands are "
                             "never run on the host"}
        if risk["risk"] == "high":
            return {"executed": False, "command": command,
                    "risk": "high", "reason": risk["reason"],
                    "available": True,
                    "error": "high-risk command requires human approval"}
        try:
            result = self.remote_runner.execute(command, timeout_s)
            out = result.get("output", "")
            if isinstance(out, str) and len(out) > self.max_output_bytes:
                result["output"] = out[: self.max_output_bytes]
                result["truncated"] = True
            result.setdefault("executed", True)
            result.setdefault("risk", risk["risk"])
            return result
        except Exception as exc:
            return {"executed": False, "command": command,
                    "available": True, "risk": risk["risk"],
                    "error": f"{type(exc).__name__}: {exc}"}

    def make_tool(self) -> Tool:
        return TerminalTool(self)


class TerminalTool(Tool):
    spec = ToolSpec("terminal", "Terminal", "Sandboxed terminal commands",
                    input_schema={"command": "string"},
                    permissions=["execute"],
                    risk_level="high", timeout_s=30,
                    resource_limits={"max_output_bytes": 200_000},
                    supported_environments=["sandboxed"],
                    approval_required=True)

    def __init__(self, sandbox: TerminalSandbox):
        self._sandbox = sandbox

    def execute(self, inputs: dict, context: Optional[dict] = None) -> dict:
        command = inputs.get("command", "")
        if not command:
            raise ToolError("command required")
        return self._sandbox.execute(
            command, timeout_s=int(inputs.get("timeout_s", 30)))