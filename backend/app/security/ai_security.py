"""AI agent security monitoring service (Volume 47).

Monitors AI agent actions, detects prompt injection in repos/issues/PRs,
validates tool calls, classifies commands, and enforces security boundaries.
"""

import re
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.security.findings_service import findings_service

logger = logging.getLogger(__name__)

UNSAFE_COMMANDS = [
    r"rm\s+-rf\s+/", r"dd\s+if=", r"mkfs\.", r":(){ :\|:& };:",
    r"chmod\s+-R\s+777", r"wget\s+\S+\s+\|\s*(?:ba)?sh",
    r"curl\s+\S+\s+\|\s*(?:ba)?sh", r"sudo\s+.*(?:rm|dd|mkfs|chmod)",
    r"iptables\s+-F", r"shutdown", r"reboot", r"init\s+0",
]

PROMPT_INJECTION_PATTERNS = [
    r"ignore\s+(?:all\s+)?(?:previous|above|prior)\s+(?:instructions?|prompts?|rules?)",
    r"disregard\s+(?:all\s+)?(?:previous|above|prior)\s+(?:instructions?|rules?)",
    r"you\s+are\s+now\s+(?:a|an)\s+",
    r"act\s+as\s+(?:if|though)\s+",
    r"pretend\s+(?:you\s+are|to\s+be)\s+",
    r"(?:system|admin)\s*prompt\s*:",
    r"<\|system\|>", r"<\|endoftext\|>",
    r"```\s*\[SYSTEM\]", r"###\s*SYSTEM\s*INSTRUCTION",
    r"bypass\s+(?:all\s+)?(?:safety|security|filters?)",
    r"disable\s+(?:all\s+)?(?:safety|security|filters?)",
    r"reveal\s+(?:your|the)\s+(?:system\s+)?prompt",
    r"what\s+(?:are|is)\s+your\s+(?:system\s+)?(?:prompt|instructions?)",
]

TOOL_CALL_RULES = [
    {"name": "tool_identity_mismatch", "description": "Tool caller claims different identity", "severity": "high"},
    {"name": "tool_scope_exceeded", "description": "Tool called outside authorized scope", "severity": "high"},
    {"name": "tool_unauthorized_network", "description": "Tool makes unauthorized network call", "severity": "high"},
    {"name": "tool_secret_access", "description": "Tool accesses secrets or credentials", "severity": "critical"},
    {"name": "tool_filesystem_traversal", "description": "Tool accesses files outside workspace", "severity": "high"},
    {"name": "tool_privilege_escalation", "description": "Tool attempts privilege escalation", "severity": "critical"},
]


class AISecurityService:
    """Monitor AI agent security, detect prompt injection, validate tool calls."""

    async def monitor_agent_action(
        self,
        db: AsyncSession,
        *,
        tenant: str,
        agent_id: str,
        action_type: str,
        action_data: dict,
        scan_id=None,
    ) -> list:
        created = []
        command = action_data.get("command", "")
        if command:
            for pattern in UNSAFE_COMMANDS:
                if re.search(pattern, command, re.IGNORECASE):
                    finding = await findings_service.create_finding(
                        db, tenant=tenant, source="ai_security", finding_type="agent",
                        severity="critical", rule="agent_unsafe_command",
                        message=f"AI agent {agent_id} attempted unsafe command: {pattern}",
                        file_path=command[:200], evidence=command[:200],
                        confidence="high", scan_id=scan_id,
                        cwe_id="CWE-78",
                    )
                    created.append(finding)

        network_calls = action_data.get("network_calls", [])
        for call in network_calls:
            url = call.get("url", "")
            if re.search(r"(?:127\.0\.0\.1|localhost|169\.254\.169\.254|metadata\.google)", url):
                finding = await findings_service.create_finding(
                    db, tenant=tenant, source="ai_security", finding_type="agent",
                    severity="high", rule="agent_ssrf_attempt",
                    message=f"AI agent {agent_id} attempted SSRF: {url[:100]}",
                    file_path=url[:200], confidence="high", scan_id=scan_id,
                    cwe_id="CWE-918",
                )
                created.append(finding)

        file_access = action_data.get("file_access", [])
        for path in file_access:
            if any(p in path for p in ("/etc/shadow", "/etc/passwd", ".ssh/", ".env", "credentials", "secrets")):
                finding = await findings_service.create_finding(
                    db, tenant=tenant, source="ai_security", finding_type="agent",
                    severity="critical", rule="agent_sensitive_file_access",
                    message=f"AI agent {agent_id} accessed sensitive file: {path}",
                    file_path=path, confidence="high", scan_id=scan_id,
                    cwe_id="CWE-200",
                )
                created.append(finding)

        return created

    async def scan_for_prompt_injection(
        self,
        db: AsyncSession,
        *,
        tenant: str,
        content: str,
        source_type: str,
        source_id: str,
        scan_id=None,
    ) -> list:
        created = []
        for pattern in PROMPT_INJECTION_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                line_no = content[:re.search(pattern, content, re.IGNORECASE).start()].count("\n") + 1
                finding = await findings_service.create_finding(
                    db, tenant=tenant, source="ai_security", finding_type="prompt_injection",
                    severity="high", rule="prompt_injection_detected",
                    message=f"Prompt injection pattern detected in {source_type}:{source_id}",
                    file_path=f"{source_type}:{source_id}", line_start=line_no,
                    evidence=pattern[:100], confidence="high", scan_id=scan_id,
                    cwe_id="CWE-77",
                )
                created.append(finding)
        return created

    async def validate_tool_call(
        self,
        db: AsyncSession,
        *,
        tenant: str,
        agent_id: str,
        tool_name: str,
        tool_args: dict,
        caller_identity: str,
        authorized_scope: list[str],
        scan_id=None,
    ) -> dict:
        violations = []

        if tool_args.get("command"):
            for pattern in UNSAFE_COMMANDS:
                if re.search(pattern, tool_args["command"], re.IGNORECASE):
                    violations.append({"rule": "tool_unsafe_command", "severity": "critical", "command": tool_args["command"][:100]})

        if tool_args.get("path"):
            path = tool_args["path"]
            if any(s in path for s in ("/etc/", "/root/", "/var/log/")):
                violations.append({"rule": "tool_filesystem_traversal", "severity": "high", "path": path})

        for v in violations:
            finding = await findings_service.create_finding(
                db, tenant=tenant, source="ai_security", finding_type="agent",
                severity=v["severity"], rule=v["rule"],
                message=f"Tool call violation for {tool_name}: {v['rule']}",
                file_path=f"{agent_id}/{tool_name}", confidence="high", scan_id=scan_id,
                cwe_id="CWE-250",
            )

        return {
            "allowed": len(violations) == 0,
            "violations": violations,
            "tool_name": tool_name,
            "agent_id": agent_id,
        }

    def classify_command(self, command: str) -> dict:
        for pattern in UNSAFE_COMMANDS:
            if re.search(pattern, command, re.IGNORECASE):
                return {"classification": "blocked", "risk": "critical", "matched_pattern": pattern}
        if any(kw in command.lower() for kw in ("sudo", "chmod", "chown", "kill", "pkill")):
            return {"classification": "review_required", "risk": "high"}
        if any(kw in command.lower() for kw in ("curl", "wget", "ssh", "scp", "rsync")):
            return {"classification": "review_required", "risk": "medium"}
        if re.search(r"\b(?:rm|mv|cp)\b", command.lower()):
            return {"classification": "review_required", "risk": "medium"}
        return {"classification": "safe", "risk": "low"}


ai_security_service = AISecurityService()
