"""CI/CD pipeline security scanning service (Volume 47).

Scans pipeline definitions for secret exposure, privileged runners,
unsafe scripts, untrusted PR execution, dependency confusion,
artifact poisoning, and unsafe cache. Integrates with Volume 46.
"""

import re
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.security.findings_service import findings_service

logger = logging.getLogger(__name__)

PIPELINE_RULES = [
    {"name": "cicd_secret_exposure", "pattern": r"(?:secrets?\.\w+|env\.\w*SECRET\w*|credentials\.\w+)", "severity": "high", "cwe": "CWE-200", "message": "Secrets referenced in pipeline (verify not logged)"},
    {"name": "cicd_privileged_runner", "pattern": r"runs-on:\s*(?:self-hosted| privileged)", "severity": "medium", "cwe": "CWE-250", "message": "Running on privileged/self-hosted runner"},
    {"name": "cicd_unsafe_script", "pattern": r"(?:run|script):\s*\|?\s*\n?\s*.*\$(?:\{.*\}|[A-Z])", "severity": "medium", "cwe": "CWE-78", "message": "Script with variable interpolation (potential injection)"},
    {"name": "cicd_untrusted_pr_merge", "pattern": r"pull_request_target.*merge|if:.*pull_request.*merge", "severity": "high", "cwe": "CWE-829", "message": "Merging untrusted PR in pull_request_target context"},
    {"name": "cicd_dependency_confusion", "pattern": r"(?:npm|pip|gem|cargo)\s+install", "severity": "low", "cwe": "CWE-494", "message": "Installing dependencies in pipeline (verify lockfiles used)"},
    {"name": "cicd_artifact_poisoning", "pattern": r"(?:uses:|download-artifact).*\$(?:\{|\()", "severity": "high", "cwe": "CWE-829", "message": "Artifact download with variable path (potential poisoning)"},
    {"name": "cicd_unsafe_cache", "pattern": r"cache:.*path:\s*\n?\s*-?\s*/", "severity": "medium", "cwe": "CWE-538", "message": "Caching absolute path (may cache sensitive data)"},
    {"name": "cicd_debug_enabled", "pattern": r"ACTIONS_STEP_DEBUG:\s*['\"]?true", "severity": "low", "cwe": "CWE-489", "message": "Debug mode enabled in CI/CD"},
    {"name": "cicd_write_all_permissions", "pattern": r"permissions:\s*\n\s*contents:\s*write", "severity": "high", "cwe": "CWE-250", "message": "Workflow has write-all permissions"},
    {"name": "cicd_checkout_full_history", "pattern": r"fetch-depth:\s*0", "severity": "low", "cwe": "CWE-200", "message": "Full git history checkout (may expose secrets)"},
    {"name": "cicd_publish_to_registry", "pattern": r"(?:docker push|npm publish|pip upload|gem push)", "severity": "medium", "cwe": "CWE-829", "message": "Publishing to registry (verify signing and provenance)"},
    {"name": "cicd_missing_if_condition", "pattern": r"on:\s*\n\s*push:\s*\n\s*branches:\s*\n\s*-?\s*['\"]?main", "severity": "low", "cwe": "CWE-829", "message": "Trigger on push to main (verify branch protection)"},
]


def scan_pipeline(content: str, filename: str = "") -> list[dict]:
    findings = []
    for rule in PIPELINE_RULES:
        try:
            for m in re.finditer(rule["pattern"], content, re.IGNORECASE | re.MULTILINE):
                line_no = content[:m.start()].count("\n") + 1
                ctx_start = max(0, m.start() - 40)
                ctx_end = min(len(content), m.end() + 40)
                evidence = content[ctx_start:ctx_end].replace("\n", " ").strip()
                findings.append({
                    "rule": rule["name"],
                    "severity": rule["severity"],
                    "cwe_id": rule.get("cwe", ""),
                    "file_path": filename,
                    "line_start": line_no,
                    "evidence": evidence[:200],
                    "message": rule["message"],
                    "confidence": "medium",
                })
        except re.error:
            continue
    return findings


class CISecurityService:
    """Scan CI/CD pipeline definitions for security issues."""

    def detect_pipeline_file(self, filename: str) -> bool:
        lower = filename.lower()
        return any(p in lower for p in (".github/workflows/", ".gitlab-ci", "jenkinsfile", ".circleci/", ".buildkite/", "azure-pipelines", "bitbucket-pipelines"))

    async def scan_pipeline_definitions(
        self,
        db: AsyncSession,
        *,
        tenant: str,
        files: dict[str, str],
        repository: str = "",
        branch: str = "main",
        commit_sha: str = "",
        scan_id=None,
    ) -> list:
        created = []
        for filename, content in files.items():
            for f in scan_pipeline(content, filename):
                finding = await findings_service.create_finding(
                    db, tenant=tenant, source="ci_cd_security", finding_type="cicd",
                    severity=f["severity"], rule=f["rule"], message=f["message"],
                    file_path=f["file_path"], line_start=f["line_start"],
                    evidence=f["evidence"], confidence=f["confidence"],
                    repository=repository, branch=branch, commit_sha=commit_sha,
                    cwe_id=f["cwe_id"], scan_id=scan_id,
                )
                created.append(finding)
        return created

    async def evaluate_runner_security(
        self,
        db: AsyncSession,
        *,
        tenant: str,
        runner_config: dict,
        scan_id=None,
    ) -> list:
        created = []
        if runner_config.get("privileged"):
            finding = await findings_service.create_finding(
                db, tenant=tenant, source="ci_cd_security", finding_type="cicd",
                severity="critical", rule="cicd_privileged_runner_config",
                message="Runner configured with privileged access",
                confidence="high", scan_id=scan_id, cwe_id="CWE-250",
            )
            created.append(finding)
        if not runner_config.get("pinned"):
            finding = await findings_service.create_finding(
                db, tenant=tenant, source="ci_cd_security", finding_type="cicd",
                severity="medium", rule="cicd_unpinned_runner",
                message="Runner version not pinned (may pull latest)",
                confidence="medium", scan_id=scan_id, cwe_id="CWE-829",
            )
            created.append(finding)
        return created


ci_security_service = CISecurityService()
