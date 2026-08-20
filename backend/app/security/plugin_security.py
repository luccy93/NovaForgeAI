"""Plugin and marketplace security service (Volume 47).

Extends marketplace security scanning for plugin validation,
MCP server validation, and permission review.
"""

import re
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.security.findings_service import findings_service

logger = logging.getLogger(__name__)

MCP_SERVER_RULES = [
    {"name": "mcp_unencrypted_transport", "severity": "high", "cwe": "CWE-319", "message": "MCP server using unencrypted transport (stdio recommended for local)"},
    {"name": "mcp_missing_auth", "severity": "medium", "cwe": "CWE-306", "message": "MCP server has no authentication configured"},
    {"name": "mcp_wildcard_tools", "severity": "high", "cwe": "CWE-250", "message": "MCP server exposes wildcard tool access"},
    {"name": "mcp_network_access", "severity": "medium", "cwe": "CWE-668", "message": "MCP server has unrestricted network access"},
    {"name": "mcp_filesystem_access", "severity": "high", "cwe": "CWE-22", "message": "MCP server has broad filesystem access"},
    {"name": "mcp_database_access", "severity": "high", "cwe": "CWE-89", "message": "MCP server has direct database access"},
]

PLUGIN_PERMISSION_RULES = {
    "filesystem": {"high_risk_patterns": [r"/etc/", r"/root/", r"/var/", r"\.ssh/", r"\.env"], "severity": "high"},
    "network": {"high_risk_patterns": [r"0\.0\.0\.0", r"metadata\.google", r"169\.254"], "severity": "medium"},
    "repository": {"high_risk_patterns": [r"force.*push", r"delete.*branch"], "severity": "high"},
    "terminal": {"high_risk_patterns": [r"sudo", r"rm\s+-rf", r"chmod", r"chown"], "severity": "critical"},
    "database": {"high_risk_patterns": [r"DROP\s+TABLE", r"DELETE\s+FROM", r"TRUNCATE"], "severity": "critical"},
    "secrets": {"high_risk_patterns": [r".*"], "severity": "critical"},
}


class PluginSecurityService:
    """Plugin/MCP security validation, permission review, marketplace scanning."""

    async def validate_plugin_permissions(
        self,
        db: AsyncSession,
        *,
        tenant: str,
        plugin_name: str,
        requested_permissions: list[str],
        scan_id=None,
    ) -> list:
        created = []
        for perm in requested_permissions:
            perm_lower = perm.lower()
            for perm_type, rule in PLUGIN_PERMISSION_RULES.items():
                if perm_type in perm_lower:
                    finding = await findings_service.create_finding(
                        db, tenant=tenant, source="plugin_security", finding_type="plugin",
                        severity=rule["severity"], rule=f"plugin_permission_{perm_type}",
                        message=f"Plugin '{plugin_name}' requests {perm_type} permission",
                        file_path=plugin_name, evidence=perm, confidence="medium",
                        scan_id=scan_id, cwe_id=rule.get("cwe", "CWE-250"),
                    )
                    created.append(finding)
        return created

    async def validate_mcp_server(
        self,
        db: AsyncSession,
        *,
        tenant: str,
        server_name: str,
        config: dict,
        scan_id=None,
    ) -> list:
        created = []
        if config.get("transport") != "stdio":
            finding = await findings_service.create_finding(
                db, tenant=tenant, source="plugin_security", finding_type="plugin",
                severity="high", rule="mcp_unencrypted_transport",
                message=f"MCP server '{server_name}' using non-stdio transport",
                file_path=server_name, confidence="high", scan_id=scan_id,
                cwe_id="CWE-319",
            )
            created.append(finding)

        if not config.get("auth"):
            finding = await findings_service.create_finding(
                db, tenant=tenant, source="plugin_security", finding_type="plugin",
                severity="medium", rule="mcp_missing_auth",
                message=f"MCP server '{server_name}' has no authentication",
                file_path=server_name, confidence="medium", scan_id=scan_id,
                cwe_id="CWE-306",
            )
            created.append(finding)

        tools = config.get("tools", [])
        if any(t.get("name") == "*" for t in tools):
            finding = await findings_service.create_finding(
                db, tenant=tenant, source="plugin_security", finding_type="plugin",
                severity="high", rule="mcp_wildcard_tools",
                message=f"MCP server '{server_name}' exposes wildcard tool access",
                file_path=server_name, confidence="high", scan_id=scan_id,
                cwe_id="CWE-250",
            )
            created.append(finding)

        network_access = config.get("network_access", {})
        if network_access.get("outbound", False):
            finding = await findings_service.create_finding(
                db, tenant=tenant, source="plugin_security", finding_type="plugin",
                severity="medium", rule="mcp_network_access",
                message=f"MCP server '{server_name}' has outbound network access",
                file_path=server_name, confidence="medium", scan_id=scan_id,
                cwe_id="CWE-668",
            )
            created.append(finding)

        return created

    async def review_plugin_code(
        self,
        db: AsyncSession,
        *,
        tenant: str,
        plugin_name: str,
        code_files: dict[str, str],
        scan_id=None,
    ) -> list:
        created = []
        sensitive_patterns = [
            (r"(?:password|secret|token|api_key)\s*[:=]\s*['\"][^'\"]{8,}['\"]", "hardcoded_secret_in_plugin", "critical"),
            (r"(?:eval|exec)\s*\(", "code_execution_in_plugin", "high"),
            (r"(?:subprocess|os\.system|os\.popen)", "system_call_in_plugin", "high"),
            (r"(?:requests?\.get|urllib)\s*\(\s*['\"]https?://", "external_http_in_plugin", "medium"),
            (r"base64\.(?:b64decode|decodebytes)", "base64_decode_in_plugin", "medium"),
        ]
        for filename, content in code_files.items():
            for pattern, rule, severity in sensitive_patterns:
                try:
                    if re.search(pattern, content, re.IGNORECASE):
                        finding = await findings_service.create_finding(
                            db, tenant=tenant, source="plugin_security", finding_type="plugin",
                            severity=severity, rule=rule,
                            message=f"Plugin '{plugin_name}' code: {rule} in {filename}",
                            file_path=f"{plugin_name}/{filename}", confidence="medium",
                            scan_id=scan_id,
                        )
                        created.append(finding)
                except re.error:
                    continue
        return created


plugin_security_service = PluginSecurityService()
