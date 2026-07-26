"""Safety system — prompt injection detection, permission validation, secret detection."""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class SafetyResult:
    allowed: bool
    reason: Optional[str] = None


class SafetyChecker:
    """Multi-layer safety checks for agent inputs and actions."""

    INJECTION_PATTERNS = [
        r"ignore\s+(?:all\s+)?(?:previous|above|prior)\s+instructions",
        r"forget\s+(?:all\s+)?(?:previous|above|prior)",
        r"system\s+prompt",
        r"you\s+are\s+(?:now|not\s+really)",
        r"pretend\s+(?:you\s+are|to\s+be)",
        r"bypass\s+(?:the\s+)?(?:safety|restrictions|rules)",
        r"override\s+(?:your\s+)?(?:instructions|programming|guidelines)",
        r"REACTIVATE",
        r"DAN\b",
        r"jailbreak",
        r"roleplay\s+as",
    ]

    SECRET_PATTERNS = [
        r"(?:api[_-]?key|apikey|secret|password|token|credential)[\s:=]+['\"]?[A-Za-z0-9_\-\.]{16,}",
        r"sk-[A-Za-z0-9]{32,}",
        r"ghp_[A-Za-z0-9]{36}",
        r"gho_[A-Za-z0-9]{36}",
        r"xox[bpsa]-[A-Za-z0-9\-]{10,}",
        r"AKIA[0-9A-Z]{16}",
        r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----",
    ]

    DESTRUCTIVE_COMMANDS = [
        r"\brm\s+-rf\b",
        r"\bdd\b",
        r"\b>\/dev\/sda\b",
        r"\bmkfs\b",
        r"\bformat\b",
        r"\b:!rm\b",
        r"\bdrop\s+database",
        r"\bdrop\s+table",
        r"\btruncate\s+table",
        r"\bpg_terminate_backend",
        r"\bshutdown\b",
        r"\breboot\b",
    ]

    async def check_input(self, task_input: str, permissions: list[str]) -> SafetyResult:
        if not task_input or not task_input.strip():
            return SafetyResult(allowed=False, reason="Empty input")

        if len(task_input) > 50000:
            return SafetyResult(allowed=False, reason="Input exceeds 50,000 character limit")

        for pattern in self.INJECTION_PATTERNS:
            if re.search(pattern, task_input, re.IGNORECASE):
                return SafetyResult(
                    allowed=False,
                    reason=f"Potential prompt injection detected: pattern matched '{pattern}'",
                )

        for pattern in self.SECRET_PATTERNS:
            if re.search(pattern, task_input, re.IGNORECASE):
                return SafetyResult(
                    allowed=False,
                    reason="Potential secret/key detected in input. Redact before submitting.",
                )

        if "write" not in permissions and "*" not in permissions:
            for pattern in self.DESTRUCTIVE_COMMANDS:
                if re.search(pattern, task_input, re.IGNORECASE):
                    return SafetyResult(
                        allowed=False,
                        reason="Destructive command detected and your agent does not have write permissions.",
                    )

        return SafetyResult(allowed=True)

    async def check_command(self, command: str) -> SafetyResult:
        for pattern in self.DESTRUCTIVE_COMMANDS:
            if re.search(pattern, command, re.IGNORECASE):
                return SafetyResult(
                    allowed=False,
                    reason=f"Destructive command blocked: matched '{pattern}'",
                )

        for pattern in self.SECRET_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return SafetyResult(allowed=False, reason="Secret detected in command")

        return SafetyResult(allowed=True)

    async def check_output(self, output: str) -> SafetyResult:
        for pattern in self.SECRET_PATTERNS:
            if re.search(pattern, output, re.IGNORECASE):
                return SafetyResult(
                    allowed=False,
                    reason="Agent output may contain secrets. Review before sharing.",
                )
        return SafetyResult(allowed=True)
