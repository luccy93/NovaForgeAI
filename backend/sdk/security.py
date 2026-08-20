"""NovaForge SDK -- Security Platform mixin (Volume 47)."""

from typing import Optional


class SecurityMixin:
    """Synchronous security platform SDK methods."""

    def security_create_scan(self, *, tenant: str = "default", scan_type: str, target_type: str, target_id: str, repository: str = "", branch: str = "main", commit_sha: str = "") -> dict:
        return self._post("/api/v1/security/scans", json={"tenant": tenant, "scan_type": scan_type, "target_type": target_type, "target_id": target_id, "repository": repository, "branch": branch, "commit_sha": commit_sha})

    def security_list_scans(self, *, tenant: str = "default", scan_type: Optional[str] = None, status: Optional[str] = None, limit: int = 50) -> list:
        params = {"tenant": tenant, "limit": limit}
        if scan_type:
            params["scan_type"] = scan_type
        if status:
            params["status"] = status
        return self._get("/api/v1/security/scans", params=params)

    def security_get_scan(self, scan_id: str) -> dict:
        return self._get(f"/api/v1/security/scans/{scan_id}")

    def security_list_findings(self, *, tenant: str = "default", severity: Optional[str] = None, status: Optional[str] = None, source: Optional[str] = None, repository: Optional[str] = None, limit: int = 50) -> list:
        params = {"tenant": tenant, "limit": limit}
        if severity:
            params["severity"] = severity
        if status:
            params["status"] = status
        if source:
            params["source"] = source
        if repository:
            params["repository"] = repository
        return self._get("/api/v1/security/findings", params=params)

    def security_findings_summary(self, tenant: str = "default") -> dict:
        return self._get("/api/v1/security/findings/summary", params={"tenant": tenant})

    def security_update_finding_status(self, finding_id: str, status: str) -> dict:
        return self._post(f"/api/v1/security/findings/{finding_id}/status", json={"status": status})

    def security_accept_risk(self, finding_id: str, authorized_by: str, reason: str) -> dict:
        return self._post(f"/api/v1/security/findings/{finding_id}/accept-risk", json={"authorized_by": authorized_by, "reason": reason})

    def security_scan_secrets(self, *, tenant: str = "default", content: str, file_path: str = "", repository: str = "") -> dict:
        return self._post("/api/v1/security/secrets/scan", json={"tenant": tenant, "content": content, "file_path": file_path, "repository": repository})

    def security_scan_sast(self, *, tenant: str = "default", content: str, file_path: str = "", repository: str = "") -> dict:
        return self._post("/api/v1/security/sast/scan", json={"tenant": tenant, "content": content, "file_path": file_path, "repository": repository})

    def security_scan_dependencies(self, *, tenant: str = "default", files: dict, repository: str = "") -> dict:
        return self._post("/api/v1/security/dependencies/scan", json={"tenant": tenant, "files": files, "repository": repository})

    def security_generate_sbom(self, *, tenant: str = "default", target_type: str, target_id: str, components: list, repository: str = "", format: str = "cyclonedx") -> dict:
        return self._post("/api/v1/security/sbom/generate", json={"tenant": tenant, "target_type": target_type, "target_id": target_id, "components": components, "repository": repository, "format": format})

    def security_get_sbom(self, sbom_id: str) -> dict:
        return self._get(f"/api/v1/security/sbom/{sbom_id}")

    def security_verify_sbom(self, sbom_id: str) -> dict:
        return self._post(f"/api/v1/security/sbom/{sbom_id}/verify")

    def security_scan_iac(self, *, tenant: str = "default", files: dict, repository: str = "") -> dict:
        return self._post("/api/v1/security/iac/scan", json={"tenant": tenant, "files": files, "repository": repository})

    def security_scan_container(self, *, tenant: str = "default", image_name: str, image_tag: str = "latest", packages: list = []) -> dict:
        return self._post("/api/v1/security/container/scan", json={"tenant": tenant, "image_name": image_name, "image_tag": image_tag, "packages": packages})

    def security_list_policies(self, tenant: str = "default") -> list:
        return self._get("/api/v1/security/policies", params={"tenant": tenant})

    def security_create_policy(self, *, tenant: str = "default", name: str, description: str = "", policy_type: str = "gate", conditions: dict = {}, actions: dict = {"decision": "warn"}) -> dict:
        return self._post("/api/v1/security/policies", json={"tenant": tenant, "name": name, "description": description, "policy_type": policy_type, "conditions": conditions, "actions": actions})

    def security_evaluate_policies(self, *, tenant: str = "default", target_type: str, target_id: str, findings: list = []) -> dict:
        return self._post("/api/v1/security/policies/evaluate", json={"tenant": tenant, "target_type": target_type, "target_id": target_id, "findings": findings})

    def security_risk_summary(self, tenant: str = "default") -> dict:
        return self._get("/api/v1/security/risk/summary", params={"tenant": tenant})

    def security_risk_score(self, tenant: str = "default") -> dict:
        return self._get("/api/v1/security/risk/score", params={"tenant": tenant})

    def security_get_provenance(self, chain_id: str, tenant: str = "default") -> dict:
        return self._get(f"/api/v1/security/provenance/{chain_id}", params={"tenant": tenant})

    def security_remediate(self, finding_id: str, tenant: str = "default", approach: str = "") -> dict:
        return self._post("/api/v1/security/remediate", json={"tenant": tenant, "finding_id": finding_id, "approach": approach})

    def security_get_remediation(self, remediation_id: str) -> dict:
        return self._get(f"/api/v1/security/remediation/{remediation_id}")

    def security_scan_cicd(self, *, tenant: str = "default", files: dict, repository: str = "") -> dict:
        return self._post("/api/v1/security/cicd/scan", json={"tenant": tenant, "files": files, "repository": repository})

    def security_monitor_agent(self, *, tenant: str = "default", agent_id: str, action_type: str, action_data: dict = {}) -> dict:
        return self._post("/api/v1/security/ai/monitor", json={"tenant": tenant, "agent_id": agent_id, "action_type": action_type, "action_data": action_data})

    def security_validate_plugin(self, *, tenant: str = "default", plugin_name: str, requested_permissions: list = []) -> dict:
        return self._post("/api/v1/security/plugin/validate", json={"tenant": tenant, "plugin_name": plugin_name, "requested_permissions": requested_permissions})

    def security_get_report(self, report_type: str, tenant: str = "default", repository: str = "", days: int = 30) -> dict:
        return self._get(f"/api/v1/security/reports/{report_type}", params={"tenant": tenant, "repository": repository, "days": days})

    def security_dashboard(self, tenant: str = "default", days: int = 30) -> dict:
        return self._get("/api/v1/security/dashboard", params={"tenant": tenant, "days": days})

    def security_search(self, q: str, tenant: str = "default", limit: int = 20) -> dict:
        return self._get("/api/v1/security/search", params={"tenant": tenant, "q": q, "limit": limit})


class AsyncSecurityMixin:
    """Asynchronous security platform SDK methods."""

    async def security_create_scan(self, *, tenant: str = "default", scan_type: str, target_type: str, target_id: str, repository: str = "", branch: str = "main", commit_sha: str = "") -> dict:
        return await self._apost("/api/v1/security/scans", json={"tenant": tenant, "scan_type": scan_type, "target_type": target_type, "target_id": target_id, "repository": repository, "branch": branch, "commit_sha": commit_sha})

    async def security_list_scans(self, *, tenant: str = "default", scan_type: Optional[str] = None, status: Optional[str] = None, limit: int = 50) -> list:
        params = {"tenant": tenant, "limit": limit}
        if scan_type:
            params["scan_type"] = scan_type
        if status:
            params["status"] = status
        return await self._aget("/api/v1/security/scans", params=params)

    async def security_get_scan(self, scan_id: str) -> dict:
        return await self._aget(f"/api/v1/security/scans/{scan_id}")

    async def security_list_findings(self, *, tenant: str = "default", severity: Optional[str] = None, status: Optional[str] = None, limit: int = 50) -> list:
        params = {"tenant": tenant, "limit": limit}
        if severity:
            params["severity"] = severity
        if status:
            params["status"] = status
        return await self._aget("/api/v1/security/findings", params=params)

    async def security_findings_summary(self, tenant: str = "default") -> dict:
        return await self._aget("/api/v1/security/findings/summary", params={"tenant": tenant})

    async def security_update_finding_status(self, finding_id: str, status: str) -> dict:
        return await self._apost(f"/api/v1/security/findings/{finding_id}/status", json={"status": status})

    async def security_scan_secrets(self, *, tenant: str = "default", content: str, file_path: str = "", repository: str = "") -> dict:
        return await self._apost("/api/v1/security/secrets/scan", json={"tenant": tenant, "content": content, "file_path": file_path, "repository": repository})

    async def security_scan_sast(self, *, tenant: str = "default", content: str, file_path: str = "", repository: str = "") -> dict:
        return await self._apost("/api/v1/security/sast/scan", json={"tenant": tenant, "content": content, "file_path": file_path, "repository": repository})

    async def security_scan_dependencies(self, *, tenant: str = "default", files: dict, repository: str = "") -> dict:
        return await self._apost("/api/v1/security/dependencies/scan", json={"tenant": tenant, "files": files, "repository": repository})

    async def security_generate_sbom(self, *, tenant: str = "default", target_type: str, target_id: str, components: list, repository: str = "", format: str = "cyclonedx") -> dict:
        return await self._apost("/api/v1/security/sbom/generate", json={"tenant": tenant, "target_type": target_type, "target_id": target_id, "components": components, "repository": repository, "format": format})

    async def security_get_sbom(self, sbom_id: str) -> dict:
        return await self._aget(f"/api/v1/security/sbom/{sbom_id}")

    async def security_scan_iac(self, *, tenant: str = "default", files: dict, repository: str = "") -> dict:
        return await self._apost("/api/v1/security/iac/scan", json={"tenant": tenant, "files": files, "repository": repository})

    async def security_scan_container(self, *, tenant: str = "default", image_name: str, image_tag: str = "latest", packages: list = []) -> dict:
        return await self._apost("/api/v1/security/container/scan", json={"tenant": tenant, "image_name": image_name, "image_tag": image_tag, "packages": packages})

    async def security_list_policies(self, tenant: str = "default") -> list:
        return await self._aget("/api/v1/security/policies", params={"tenant": tenant})

    async def security_create_policy(self, *, tenant: str = "default", name: str, description: str = "", conditions: dict = {}, actions: dict = {"decision": "warn"}) -> dict:
        return await self._apost("/api/v1/security/policies", json={"tenant": tenant, "name": name, "description": description, "conditions": conditions, "actions": actions})

    async def security_evaluate_policies(self, *, tenant: str = "default", target_type: str, target_id: str, findings: list = []) -> dict:
        return await self._apost("/api/v1/security/policies/evaluate", json={"tenant": tenant, "target_type": target_type, "target_id": target_id, "findings": findings})

    async def security_risk_summary(self, tenant: str = "default") -> dict:
        return await self._aget("/api/v1/security/risk/summary", params={"tenant": tenant})

    async def security_get_provenance(self, chain_id: str, tenant: str = "default") -> dict:
        return await self._aget(f"/api/v1/security/provenance/{chain_id}", params={"tenant": tenant})

    async def security_remediate(self, finding_id: str, tenant: str = "default", approach: str = "") -> dict:
        return await self._apost("/api/v1/security/remediate", json={"tenant": tenant, "finding_id": finding_id, "approach": approach})

    async def security_scan_cicd(self, *, tenant: str = "default", files: dict, repository: str = "") -> dict:
        return await self._apost("/api/v1/security/cicd/scan", json={"tenant": tenant, "files": files, "repository": repository})

    async def security_monitor_agent(self, *, tenant: str = "default", agent_id: str, action_type: str, action_data: dict = {}) -> dict:
        return await self._apost("/api/v1/security/ai/monitor", json={"tenant": tenant, "agent_id": agent_id, "action_type": action_type, "action_data": action_data})

    async def security_validate_plugin(self, *, tenant: str = "default", plugin_name: str, requested_permissions: list = []) -> dict:
        return await self._apost("/api/v1/security/plugin/validate", json={"tenant": tenant, "plugin_name": plugin_name, "requested_permissions": requested_permissions})

    async def security_get_report(self, report_type: str, tenant: str = "default", repository: str = "", days: int = 30) -> dict:
        return await self._aget(f"/api/v1/security/reports/{report_type}", params={"tenant": tenant, "repository": repository, "days": days})

    async def security_dashboard(self, tenant: str = "default", days: int = 30) -> dict:
        return await self._aget("/api/v1/security/dashboard", params={"tenant": tenant, "days": days})

    async def security_search(self, q: str, tenant: str = "default", limit: int = 20) -> dict:
        return await self._aget("/api/v1/security/search", params={"tenant": tenant, "q": q, "limit": limit})
