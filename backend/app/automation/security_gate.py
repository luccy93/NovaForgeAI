"""Security gate for autonomous changes.

Runs SAST, SCA, secret scanning, and policy checks before delivery.
Critical findings block delivery according to policy.
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

SECRET_PATTERNS = [
    re.compile(r"(?:api[_-]?key|secret|token|password)\s*[=:]\s*['\"]([^\s'\"]+)", re.IGNORECASE),
    re.compile(r"AKIA[0-9A-Z]{16}", re.IGNORECASE),
    re.compile(r"ghp_[A-Za-z0-9]{36}"),
    re.compile(r"sk-[A-Za-z0-9]{32,}"),
    re.compile(r"xox[bpsa]-[A-Za-z0-9-]+"),
]

SAST_PATTERNS = {
    "eval_usage": re.compile(r"\beval\s*\("),
    "exec_usage": re.compile(r"\bexec\s*\("),
    "sql_injection": re.compile(r"(?:execute|cursor\.execute)\s*\(\s*[\"'].*%s", re.IGNORECASE),
    "hardcoded_password": re.compile(r"password\s*=\s*['\"][^'\"]+['\"]", re.IGNORECASE),
    "disable_ssl": re.compile(r"verify\s*=\s*False|CERT_NONE|ssl\.PROTOCOL_TLS"),
    "debug_mode": re.compile(r"DEBUG\s*=\s*True|debug\s*=\s*True"),
}

BLOCKED_FINDINGS = {"hardcoded_password", "sql_injection", "eval_usage"}


class SecurityGate:
    def __init__(self, blocked_patterns: Optional[set] = None):
        self.blocked_patterns = blocked_patterns or BLOCKED_FINDINGS

    def scan_diff(self, diff: str) -> dict:
        findings = []
        secrets_found = []
        for pattern in SECRET_PATTERNS:
            matches = pattern.findall(diff)
            if matches:
                secrets_found.extend(matches)
        if secrets_found:
            findings.append({
                "type": "secret_exposure",
                "severity": "critical",
                "message": f"Potential secrets detected in diff",
                "count": len(secrets_found),
            })

        for rule_id, pattern in SAST_PATTERNS.items():
            matches = pattern.findall(diff)
            if matches:
                severity = "critical" if rule_id in self.blocked_patterns else "warning"
                findings.append({
                    "type": rule_id,
                    "severity": severity,
                    "message": f"SAST finding: {rule_id}",
                    "count": len(matches),
                })
        has_critical = any(f["severity"] == "critical" for f in findings)
        return {
            "clean": len(findings) == 0,
            "findings": findings,
            "critical_count": sum(1 for f in findings if f["severity"] == "critical"),
            "warning_count": sum(1 for f in findings if f["severity"] == "warning"),
            "blocks_delivery": has_critical,
        }

    def scan_file_changes(self, file_changes: list[dict]) -> dict:
        all_findings = []
        for fc in file_changes:
            content = fc.get("content", "")
            path = fc.get("path", "unknown")
            result = self.scan_diff(content)
            for f in result["findings"]:
                f["file"] = path
            all_findings.extend(result["findings"])
        has_critical = any(f["severity"] == "critical" for f in all_findings)
        return {
            "clean": len(all_findings) == 0,
            "findings": all_findings,
            "blocks_delivery": has_critical,
        }

    def validate_patch(self, diff: str, file_changes: Optional[list] = None) -> dict:
        diff_result = self.scan_diff(diff)
        file_result = {"clean": True, "findings": [], "blocks_delivery": False}
        if file_changes:
            file_result = self.scan_file_changes(file_changes)
        all_findings = diff_result["findings"] + file_result["findings"]
        return {
            "clean": diff_result["clean"] and file_result["clean"],
            "findings": all_findings,
            "blocks_delivery": diff_result["blocks_delivery"] or file_result["blocks_delivery"],
            "critical_count": sum(1 for f in all_findings if f["severity"] == "critical"),
            "warning_count": sum(1 for f in all_findings if f["severity"] == "warning"),
        }
