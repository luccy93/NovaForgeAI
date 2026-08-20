"""Infrastructure-as-Code scanning service (Volume 47).

Scans Dockerfiles, Kubernetes YAML, Terraform HCL, and Helm charts
for security misconfigurations.
"""

import re
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.security.findings_service import findings_service

logger = logging.getLogger(__name__)

DOCKERFILE_RULES = [
    {"name": "dockerfile_root_user", "pattern": r"^USER\s+root", "severity": "high", "cwe": "CWE-250", "message": "Container runs as root user"},
    {"name": "dockerfile_privileged", "pattern": r"--privileged", "severity": "critical", "cwe": "CWE-250", "message": "Privileged mode enabled"},
    {"name": "dockerfile_add_remote", "pattern": r"^ADD\s+https?://", "severity": "medium", "cwe": "CWE-829", "message": "ADD fetches remote URL (prefer COPY + RUN curl)"},
    {"name": "dockerfile_secrets_in_env", "pattern": r"^ENV\s+\w*(?:SECRET|PASSWORD|TOKEN|API_KEY|KEY)\w*\s*=", "severity": "critical", "cwe": "CWE-312", "message": "Secret in ENV instruction"},
    {"name": "dockerfile_curl_pipe_bash", "pattern": r"curl.*\|\s*(?:ba)?sh", "severity": "high", "cwe": "CWE-829", "message": "Piping curl to shell"},
    {"name": "dockerfile_add_local", "pattern": r"^ADD\s+\.", "severity": "low", "cwe": "CWE-829", "message": "ADD with local files (prefer COPY)"},
    {"name": "dockerfile_exposed_port", "pattern": r"^EXPOSE\s+", "severity": "informational", "cwe": "CWE-16", "message": "Port exposed -- verify it is intended"},
    {"name": "dockerfile_healthcheck_missing", "pattern": r"^FROM\s+", "severity": "low", "cwe": "CWE-693", "message": "Ensure HEALTHCHECK is defined"},
    {"name": "dockerfile_latest_tag", "pattern": r"^FROM\s+\S+:latest", "severity": "medium", "cwe": "CWE-829", "message": "Using :latest tag (pin to specific version)"},
    {"name": "dockerfile_sensitive_mount", "pattern": r"-v\s+/etc/(?:passwd|shadow|sudoers)", "severity": "critical", "cwe": "CWE-250", "message": "Mounting sensitive host files"},
    {"name": "dockerfile_wget_insecure", "pattern": r"wget\s+--no-check-certificate", "severity": "high", "cwe": "CWE-295", "message": "wget with certificate verification disabled"},
    {"name": "dockerfile_debugger_installed", "pattern": r"RUN\s+.*(?:apt-get|yum|apk)\s+install.*(?:gdb|strace|ltrace)", "severity": "medium", "cwe": "CWE-215", "message": "Debug tools installed in container"},
]

KUBERNETES_RULES = [
    {"name": "k8s_privileged_container", "pattern": r"privileged:\s*true", "severity": "critical", "cwe": "CWE-250", "message": "Privileged container"},
    {"name": "k8s_host_network", "pattern": r"hostNetwork:\s*true", "severity": "high", "cwe": "CWE-668", "message": "Host network access enabled"},
    {"name": "k8s_host_pid", "pattern": r"hostPID:\s*true", "severity": "high", "cwe": "CWE-250", "message": "Host PID namespace shared"},
    {"name": "k8s_host_ipc", "pattern": r"hostIPC:\s*true", "severity": "high", "cwe": "CWE-250", "message": "Host IPC namespace shared"},
    {"name": "k8s_host_port", "pattern": r"hostPort:", "severity": "medium", "cwe": "CWE-668", "message": "hostPort exposes container on host"},
    {"name": "k8s_allow_privilege_escalation", "pattern": r"allowPrivilegeEscalation:\s*true", "severity": "high", "cwe": "CWE-269", "message": "Privilege escalation allowed"},
    {"name": "k8s_caps_add_all", "pattern": r"capabilities:\s*\n\s*add:\s*\n\s*- ALL", "severity": "critical", "cwe": "CWE-250", "message": "All capabilities added"},
    {"name": "k8s_caps_add_sys_admin", "pattern": r"- SYS_ADMIN", "severity": "critical", "cwe": "CWE-250", "message": "SYS_ADMIN capability added"},
    {"name": "k8s_caps_add_net_raw", "pattern": r"- NET_RAW", "severity": "high", "cwe": "CWE-250", "message": "NET_RAW capability added"},
    {"name": "k8s_run_as_root", "pattern": r"runAsUser:\s*0", "severity": "high", "cwe": "CWE-250", "message": "Container runs as root"},
    {"name": "k8s_read_only_rootfs_missing", "pattern": r"securityContext:", "severity": "low", "cwe": "CWE-732", "message": "Verify readOnlyRootFilesystem is true"},
    {"name": "k8s_no_resource_limits", "pattern": r"resources:", "severity": "medium", "cwe": "CWE-770", "message": "Ensure resource limits are set"},
    {"name": "k8s_default_namespace", "pattern": r"namespace:\s*default", "severity": "low", "cwe": "CWE-668", "message": "Using default namespace"},
    {"name": "k8s_wildcard_role", "pattern": r"resources:\s*\n\s*- '\*'", "severity": "high", "cwe": "CWE-250", "message": "Wildcard resource access in RBAC"},
    {"name": "k8s_secret_in_yaml", "pattern": r"(?:password|secret|token|key)\s*:\s*[A-Za-z0-9+/=_-]{8,}", "severity": "critical", "cwe": "CWE-312", "message": "Potential secret value in YAML"},
    {"name": "k8s_no_security_context", "pattern": r"kind:\s*(?:Deployment|StatefulSet|DaemonSet)", "severity": "low", "cwe": "CWE-250", "message": "Ensure securityContext is defined"},
]

TERRAFORM_RULES = [
    {"name": "tf_public_s3", "pattern": r"acl\s*=\s*[\"']public", "severity": "critical", "cwe": "CWE-284", "message": "S3 bucket with public ACL"},
    {"name": "tf_public_acl", "pattern": r"acl\s*=\s*[\"']public-read", "severity": "high", "cwe": "CWE-284", "message": "Public read ACL"},
    {"name": "tf_open_security_group", "pattern": r"cidr_blocks\s*=\s*\[\s*[\"']0\.0\.0\.0/0[\"']\s*\]", "severity": "high", "cwe": "CWE-284", "message": "Security group open to 0.0.0.0/0"},
    {"name": "tf_overprivileged_iam", "pattern": r'"Action"\s*:\s*"\*"', "severity": "critical", "cwe": "CWE-250", "message": "IAM policy grants all actions"},
    {"name": "tf_wildcard_resource", "pattern": r'"Resource"\s*:\s*"\*"', "severity": "high", "cwe": "CWE-250", "message": "IAM policy applies to all resources"},
    {"name": "tf_unencrypted_ebs", "pattern": r"encrypted\s*=\s*false", "severity": "high", "cwe": "CWE-311", "message": "EBS volume encryption disabled"},
    {"name": "tf_unencrypted_s3", "pattern": r"server_side_encryption_configuration", "severity": "medium", "cwe": "CWE-311", "message": "Verify S3 server-side encryption is enabled"},
    {"name": "tf_public_rds", "pattern": r"publicly_accessible\s*=\s*true", "severity": "critical", "cwe": "CWE-284", "message": "RDS instance publicly accessible"},
    {"name": "tf_no_logging", "pattern": r"logging\s*\{", "severity": "low", "cwe": "CWE-778", "message": "Verify logging is enabled"},
    {"name": "tf_iam_user_access_keys", "pattern": r"aws_iam_access_key", "severity": "medium", "cwe": "CWE-798", "message": "IAM user access keys created (prefer IAM roles)"},
]


def scan_dockerfile(content: str, file_path: str = "") -> list[dict]:
    return _scan_patterns(content, file_path, DOCKERFILE_RULES, "iac")


def scan_kubernetes(content: str, file_path: str = "") -> list[dict]:
    return _scan_patterns(content, file_path, KUBERNETES_RULES, "iac")


def scan_terraform(content: str, file_path: str = "") -> list[dict]:
    return _scan_patterns(content, file_path, TERRAFORM_RULES, "iac")


def _scan_patterns(content: str, file_path: str, rules: list[dict], finding_type: str) -> list[dict]:
    findings = []
    for rule in rules:
        try:
            for m in re.finditer(rule["pattern"], content, re.IGNORECASE | re.MULTILINE):
                line_no = content[:m.start()].count("\n") + 1
                ctx_start = max(0, m.start() - 30)
                ctx_end = min(len(content), m.end() + 30)
                evidence = content[ctx_start:ctx_end].replace("\n", " ").strip()
                findings.append({
                    "rule": rule["name"],
                    "severity": rule["severity"],
                    "cwe_id": rule.get("cwe", ""),
                    "file_path": file_path,
                    "line_start": line_no,
                    "evidence": evidence[:200],
                    "message": rule["message"],
                    "confidence": "high",
                    "finding_type": finding_type,
                })
        except re.error:
            continue
    return findings


class IaCScanner:
    """Scan Dockerfiles, Kubernetes YAML, Terraform for security issues."""

    def detect_file_type(self, filename: str) -> str | None:
        if filename.lower() in ("dockerfile", "dockerfile.dev", "dockerfile.prod"):
            return "dockerfile"
        if filename.endswith((".yaml", ".yml")):
            return "kubernetes"
        if filename.endswith((".tf", ".tf.json")):
            return "terraform"
        return None

    def scan_file(self, filename: str, content: str) -> list[dict]:
        ft = self.detect_file_type(filename)
        if ft == "dockerfile":
            return scan_dockerfile(content, filename)
        if ft == "kubernetes":
            return scan_kubernetes(content, filename)
        if ft == "terraform":
            return scan_terraform(content, filename)
        return []

    async def scan_files(
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
            for f in self.scan_file(filename, content):
                finding = await findings_service.create_finding(
                    db,
                    tenant=tenant,
                    source="iac_scanner",
                    finding_type=f["finding_type"],
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


iac_scanner = IaCScanner()
