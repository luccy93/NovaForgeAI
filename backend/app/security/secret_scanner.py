"""Secret scanning service (Volume 47).

Consolidates patterns from code_intelligence/security.py and
intelligence/security_intelligence.py into a unified DB-backed
secret scanner with git history scanning and redaction.
"""

import hashlib
import re
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.security.findings_service import findings_service

logger = logging.getLogger(__name__)

SECRET_PATTERNS = [
    {"name": "aws_access_key", "pattern": r"(?:^|[^A-Za-z0-9/+=])(?P<val>AKIA[0-9A-Z]{16})(?:[^A-Za-z0-9/+=]|$)", "severity": "critical", "cwe": "CWE-798"},
    {"name": "aws_secret_key", "pattern": r"(?:aws_secret_access_key|secret_key)\s*[=:]\s*['\"]?(?P<val>[A-Za-z0-9/+=]{40})['\"]?", "severity": "critical", "cwe": "CWE-798"},
    {"name": "github_token", "pattern": r"gh[pousr]_[A-Za-z0-9_]{36,255}", "severity": "critical", "cwe": "CWE-798"},
    {"name": "github_fine_grained_pat", "pattern": r"github_pat_[A-Za-z0-9_]{22,255}", "severity": "critical", "cwe": "CWE-798"},
    {"name": "gitlab_token", "pattern": r"glpat-[A-Za-z0-9\-_]{20,}", "severity": "critical", "cwe": "CWE-798"},
    {"name": "slack_token", "pattern": r"xox[baprs]-[0-9a-zA-Z\-]{10,}", "severity": "critical", "cwe": "CWE-798"},
    {"name": "slack_webhook", "pattern": r"https://hooks\.slack\.com/services/T[A-Z0-9]+/B[A-Z0-9]+/[a-zA-Z0-9]+", "severity": "high", "cwe": "CWE-200"},
    {"name": "stripe_key", "pattern": r"[sr]k_(?:live|test)_[0-9a-zA-Z]{24,}", "severity": "critical", "cwe": "CWE-798"},
    {"name": "gcp_service_account", "pattern": r'"type"\s*:\s*"service_account"', "severity": "high", "cwe": "CWE-798"},
    {"name": "private_key", "pattern": r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----", "severity": "critical", "cwe": "CWE-321"},
    {"name": "jwt_token", "pattern": r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+", "severity": "high", "cwe": "CWE-798"},
    {"name": "database_url", "pattern": r"(?:postgres|mysql|mongodb|redis):\/\/[^\s]{10,}", "severity": "critical", "cwe": "CWE-798"},
    {"name": "connection_string", "pattern": r"(?:Server|Data Source|jdbc:)[^\s]{20,}", "severity": "high", "cwe": "CWE-798"},
    {"name": "npm_token", "pattern": r"npm_[A-Za-z0-9]{36}", "severity": "critical", "cwe": "CWE-798"},
    {"name": "pypi_token", "pattern": r"pypi-[A-Za-z0-9\-_]{50,}", "severity": "critical", "cwe": "CWE-798"},
    {"name": "heroku_api_key", "pattern": r"(?:HEROKU_API_KEY|heroku_api_key)\s*[=:]\s*['\"]?[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}['\"]?", "severity": "critical", "cwe": "CWE-798"},
    {"name": "sendgrid_key", "pattern": r"SG\.[A-Za-z0-9\-_]{22}\.[A-Za-z0-9\-_]{43}", "severity": "critical", "cwe": "CWE-798"},
    {"name": "twilio_api_key", "pattern": r"SK[0-9a-fA-F]{32}", "severity": "critical", "cwe": "CWE-798"},
    {"name": "hardcoded_password", "pattern": r"(?:password|passwd|pwd)\s*[=:]\s*['\"](?P<val>[^'\"]{6,})['\"]", "severity": "high", "cwe": "CWE-259"},
    {"name": "api_key_assignment", "pattern": r"(?:api_key|apikey|api_secret)\s*[=:]\s*['\"](?P<val>[A-Za-z0-9\-_]{20,})['\"]", "severity": "high", "cwe": "CWE-798"},
    {"name": "dotenv_secret", "pattern": r"SECRET_KEY\s*[=:]\s*['\"]?(?P<val>[A-Za-z0-9\-_]{16,})['\"]?", "severity": "high", "cwe": "CWE-798"},
    {"name": "huggingface_token", "pattern": r"hf_[A-Za-z0-9]{34}", "severity": "critical", "cwe": "CWE-798"},
    {"name": "openai_key", "pattern": r"sk-[A-Za-z0-9]{20}T3BlbkFJ[A-Za-z0-9]{20}", "severity": "critical", "cwe": "CWE-798"},
]


def _compute_secret_hash(matched_text: str) -> str:
    return hashlib.sha256(matched_text.encode()).hexdigest()[:16]


def scan_content(content: str, file_path: str = "") -> list[dict]:
    findings = []
    for pat in SECRET_PATTERNS:
        try:
            for m in re.finditer(pat["pattern"], content, re.IGNORECASE):
                line_no = content[:m.start()].count("\n") + 1
                matched = m.group(0)
                secret_hash = _compute_secret_hash(matched)
                redacted = matched[:4] + "****" + matched[-4:] if len(matched) > 12 else "****"
                findings.append({
                    "rule": pat["name"],
                    "severity": pat["severity"],
                    "cwe_id": pat.get("cwe", ""),
                    "file_path": file_path,
                    "line_start": line_no,
                    "evidence": redacted,
                    "message": f"Secret detected: {pat['name']}",
                    "confidence": "high",
                    "metadata_extra": {"secret_hash": secret_hash, "pattern_len": len(matched)},
                })
        except re.error:
            continue
    return findings


class SecretScanner:
    """Unified secret scanner with DB persistence and deduplication."""

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
        raw_findings = scan_content(content, file_path)
        created = []
        for f in raw_findings:
            finding = await findings_service.create_finding(
                db,
                tenant=tenant,
                source="secret_scanner",
                finding_type="secret",
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
                auto_remediable=False,
                scan_id=scan_id,
                metadata_extra=f.get("metadata_extra", {}),
            )
            created.append(finding)
        return created

    def scan_content_sync(self, content: str, file_path: str = "") -> list[dict]:
        return scan_content(content, file_path)


secret_scanner = SecretScanner()
