"""SAST scanner service (Volume 47).

Consolidates static analysis patterns from code_intelligence/security.py
and intelligence/security_intelligence.py into a unified DB-backed scanner.
"""

import re
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.security.findings_service import findings_service

logger = logging.getLogger(__name__)

INJECTION_PATTERNS = [
    {"name": "sql_injection", "pattern": r"(?:execute|cursor\.execute|raw|rawquery)\s*\(\s*[\"f'].*(?:%s|{|\+)", "severity": "high", "cwe": "CWE-89", "message": "Potential SQL injection via string formatting"},
    {"name": "command_injection", "pattern": r"(?:os\.system|subprocess\.call|subprocess\.run|subprocess\.Popen|eval|exec)\s*\(", "severity": "high", "cwe": "CWE-78", "message": "Potential command injection"},
    {"name": "xss_reflected", "pattern": r"(?:innerHTML|outerHTML|document\.write|\.html\()\s*.*\+", "severity": "medium", "cwe": "CWE-79", "message": "Potential reflected XSS"},
    {"name": "path_traversal", "pattern": r"(?:open|read|write)\s*\(\s*.*(?:\.\.\/|\.\.\\)", "severity": "high", "cwe": "CWE-22", "message": "Potential path traversal"},
    {"name": "code_injection", "pattern": r"(?:eval|exec|compile)\s*\(\s*(?!['\"])", "severity": "critical", "cwe": "CWE-94", "message": "Potential code injection via eval/exec"},
    {"name": "template_injection", "pattern": r"(?:Template|render_template_string)\s*\(.*\+", "severity": "high", "cwe": "CWE-1336", "message": "Potential template injection"},
    {"name": "ldap_injection", "pattern": r"(?:ldap_search|ldap\.filter)\s*\(.*\+", "severity": "high", "cwe": "CWE-90", "message": "Potential LDAP injection"},
    {"name": "nosql_injection", "pattern": r"\.(?:where|find|update|delete)\s*\(\s*\{.*\$\w+\s*:", "severity": "high", "cwe": "CWE-943", "message": "Potential NoSQL injection"},
    {"name": "regex_dos", "pattern": r"re\.compile\s*\(.*\+.*\+.*re\.", "severity": "medium", "cwe": "CWE-1333", "message": "Potential regex DoS"},
    {"name": "deserialization", "pattern": r"(?:pickle\.loads|yaml\.load|marshal\.loads|shelve\.open)", "severity": "high", "cwe": "CWE-502", "message": "Unsafe deserialization"},
]

INSECURE_PATTERNS = [
    {"name": "insecure_random", "pattern": r"(?:random\.random|random\.randint|random\.choice)\s*\(", "severity": "low", "cwe": "CWE-330", "message": "Insecure randomness (use secrets module)"},
    {"name": "hardcoded_ip", "pattern": r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b", "severity": "low", "cwe": "CWE-200", "message": "Hardcoded IP address"},
    {"name": "debug_enabled", "pattern": r"DEBUG\s*[=:]\s*(?:True|1|\"true\")", "severity": "medium", "cwe": "CWE-489", "message": "Debug mode enabled in code"},
    {"name": "ssl_verify_disabled", "pattern": r"verify\s*[=:]\s*False", "severity": "high", "cwe": "CWE-295", "message": "SSL verification disabled"},
    {"name": "cors_wildcard", "pattern": r"Access-Control-Allow-Origin.*\*", "severity": "medium", "cwe": "CWE-942", "message": "CORS wildcard origin"},
    {"name": "insecure_cookie", "pattern": r"set_cookie\s*\(.*(?:secure\s*=\s*False|httponly\s*=\s*False)", "severity": "medium", "cwe": "CWE-614", "message": "Insecure cookie configuration"},
    {"name": "weak_hash", "pattern": r"(?:hashlib\.md5|hashlib\.sha1)\s*\(", "severity": "low", "cwe": "CWE-328", "message": "Weak hash algorithm"},
    {"name": "assert_used_for_auth", "pattern": r"assert\s+.*(?:user|token|auth|permission)", "severity": "medium", "cwe": "CWE-617", "message": "Assert used for authorization check"},
    {"name": "binding_to_all_interfaces", "pattern": r"bind\s*\(\s*['\"]0\.0\.0\.0['\"]", "severity": "medium", "cwe": "CWE-668", "message": "Binding to all network interfaces"},
    {"name": "insecure_tempfile", "pattern": r"(?:tempfile\.mktemp|tmp\s*=.*\/tmp\/)", "severity": "medium", "cwe": "CWE-377", "message": "Insecure temporary file"},
    {"name": "hardcoded_secret_in_config", "pattern": r"(?:secret|token|password|api_key)\s*[:=]\s*['\"][A-Za-z0-9+/=_-]{16,}['\"]", "severity": "high", "cwe": "CWE-798", "message": "Hardcoded secret in configuration"},
]

MISCONFIGURATION_PATTERNS = [
    {"name": "missing_security_headers", "pattern": r"(?:@app\.route|@router\.)\s*.*\ndef.*response", "severity": "low", "cwe": "CWE-693", "message": "Verify security headers are set on responses"},
    {"name": "exposed_error_details", "pattern": r"traceback\.format_exc|str\(e\)|exc_info\s*=\s*True", "severity": "medium", "cwe": "CWE-209", "message": "Error details may be exposed to users"},
    {"name": "unvalidated_redirect", "pattern": r"redirect\s*\(.*request\.", "severity": "medium", "cwe": "CWE-601", "message": "Potential unvalidated redirect"},
    {"name": "directory_listing", "pattern": r"(?:directory_listing|autoindex)\s*[=:]\s*(?:True|1)", "severity": "medium", "cwe": "CWE-548", "message": "Directory listing enabled"},
    {"name": "admin_exposed", "pattern": r"(?:\/admin|\/debug|\/_debug|\/console)", "severity": "low", "cwe": "CWE-215", "message": "Admin/debug endpoint exposed"},
]


def scan_ast(content: str, file_path: str = "") -> list[dict]:
    findings = []
    all_patterns = INJECTION_PATTERNS + INSECURE_PATTERNS + MISCONFIGURATION_PATTERNS
    for pat in all_patterns:
        try:
            for m in re.finditer(pat["pattern"], content, re.IGNORECASE | re.MULTILINE):
                line_no = content[:m.start()].count("\n") + 1
                context_start = max(0, m.start() - 40)
                context_end = min(len(content), m.end() + 40)
                evidence = content[context_start:context_end].replace("\n", " ").strip()
                findings.append({
                    "rule": pat["name"],
                    "severity": pat["severity"],
                    "cwe_id": pat.get("cwe", ""),
                    "file_path": file_path,
                    "line_start": line_no,
                    "evidence": evidence[:200],
                    "message": pat["message"],
                    "confidence": "medium" if pat["severity"] in ("low", "medium") else "high",
                })
        except re.error:
            continue
    return findings


class SASTScanner:
    """Unified SAST scanner with DB persistence and deduplication."""

    async def scan_content(
        self,
        db: AsyncSession,
        *,
        tenant: str,
        content: str,
        file_path: str = "",
        repository: str = "",
        branch: str = "main",
        commit_sha: str = "",
        scan_id=None,
    ) -> list:
        raw_findings = scan_ast(content, file_path)
        created = []
        for f in raw_findings:
            finding = await findings_service.create_finding(
                db,
                tenant=tenant,
                source="sast_scanner",
                finding_type="sast",
                severity=f["severity"],
                rule=f["rule"],
                message=f["message"],
                file_path=f["file_path"],
                line_start=f["line_start"],
                evidence=f["evidence"],
                confidence=f["confidence"],
                repository=repository,
                branch=branch,
                commit_sha=commit_sha,
                cwe_id=f["cwe_id"],
                scan_id=scan_id,
            )
            created.append(finding)
        return created

    def scan_content_sync(self, content: str, file_path: str = "") -> list[dict]:
        return scan_ast(content, file_path)


sast_scanner = SASTScanner()
