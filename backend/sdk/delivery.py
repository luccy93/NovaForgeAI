"""Delivery Platform SDK mixin (Volume 46)."""

from typing import Any, Optional
from uuid import UUID


class DeliveryMixin:
    """Sync delivery operations mixed into NovaForgeClient."""

    def create_pipeline(self, tenant: str, project: str, repository: str, branch: str,
                        name: str, **kwargs) -> dict:
        return self._request("POST", "/delivery/pipelines", json={
            "tenant": tenant, "project": project, "repository": repository,
            "branch": branch, "name": name, **kwargs,
        })

    def list_pipelines(self, tenant: Optional[str] = None, limit: int = 50, offset: int = 0) -> list[dict]:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if tenant:
            params["tenant"] = tenant
        return self._request("GET", "/delivery/pipelines", params=params)

    def get_pipeline(self, pipeline_id: str | UUID) -> dict:
        return self._request("GET", f"/delivery/pipelines/{pipeline_id}")

    def trigger_pipeline_run(self, pipeline_id: str | UUID, commit_sha: str = "",
                              actor: str = "sdk") -> dict:
        return self._request("POST", f"/delivery/pipelines/{pipeline_id}/run", json={
            "commit_sha": commit_sha, "actor": actor,
        })

    def list_pipeline_runs(self, pipeline_id: str | UUID, limit: int = 20) -> list[dict]:
        return self._request("GET", f"/delivery/pipelines/{pipeline_id}/runs", params={"limit": limit})

    def list_jobs(self, run_id: str | UUID) -> list[dict]:
        return self._request("GET", f"/delivery/runs/{run_id}/jobs")

    def create_runner(self, name: str, region: str = "default", runner_type: str = "ephemeral",
                      **kwargs) -> dict:
        return self._request("POST", "/delivery/runners", json={
            "name": name, "region": region, "runner_type": runner_type, **kwargs,
        })

    def list_runners(self, tenant: Optional[str] = None, limit: int = 50) -> list[dict]:
        params: dict[str, Any] = {"limit": limit}
        if tenant:
            params["tenant"] = tenant
        return self._request("GET", "/delivery/runners", params=params)

    def runner_heartbeat(self, runner_id: str | UUID) -> dict:
        return self._request("POST", f"/delivery/runners/{runner_id}/heartbeat")

    def create_artifact(self, name: str, artifact_type: str, hash_val: str,
                        version: str = "0.0.0", repository: str = "", **kwargs) -> dict:
        return self._request("POST", "/delivery/artifacts", json={
            "name": name, "artifact_type": artifact_type, "hash": hash_val,
            "version": version, "repository": repository, **kwargs,
        })

    def verify_artifact(self, artifact_id: str | UUID, expected_hash: str) -> dict:
        return self._request("GET", f"/delivery/artifacts/{artifact_id}/verify",
                             params={"expected_hash": expected_hash})

    def create_environment(self, tenant: str, name: str, env_type: str, **kwargs) -> dict:
        return self._request("POST", "/delivery/environments", json={
            "tenant": tenant, "name": name, "env_type": env_type, **kwargs,
        })

    def list_environments(self, tenant: Optional[str] = None) -> list[dict]:
        params: dict[str, Any] = {}
        if tenant:
            params["tenant"] = tenant
        return self._request("GET", "/delivery/environments", params=params)

    def freeze_environment(self, env_id: str | UUID, reason: str = "") -> dict:
        return self._request("POST", f"/delivery/environments/{env_id}/freeze", params={"reason": reason})

    def can_deploy(self, env_id: str | UUID) -> dict:
        return self._request("GET", f"/delivery/environments/{env_id}/can-deploy")

    def create_deployment(self, environment_id: str | UUID, strategy: str = "rolling",
                          version: str = "0.0.0", **kwargs) -> dict:
        return self._request("POST", "/delivery/deployments", json={
            "environment_id": str(environment_id), "strategy": strategy,
            "version": version, **kwargs,
        })

    def list_deployments(self, tenant: Optional[str] = None, status: Optional[str] = None,
                         limit: int = 20) -> list[dict]:
        params: dict[str, Any] = {"limit": limit}
        if tenant:
            params["tenant"] = tenant
        if status:
            params["status"] = status
        return self._request("GET", "/delivery/deployments", params=params)

    def start_deployment(self, deployment_id: str | UUID) -> dict:
        return self._request("POST", f"/delivery/deployments/{deployment_id}/start")

    def complete_deployment(self, deployment_id: str | UUID, health_status: str = "healthy") -> dict:
        return self._request("POST", f"/delivery/deployments/{deployment_id}/complete",
                             params={"health_status": health_status})

    def approve_deployment(self, deployment_id: str | UUID) -> dict:
        return self._request("POST", f"/delivery/deployments/{deployment_id}/approve")

    def rollback_deployment(self, deployment_id: str | UUID, reason: str = "") -> dict:
        return self._request("POST", f"/delivery/deployments/{deployment_id}/rollback", json={"reason": reason})

    def create_release(self, tenant: str, project: str, repository: str, version: str, **kwargs) -> dict:
        return self._request("POST", "/delivery/releases", json={
            "tenant": tenant, "project": project, "repository": repository,
            "version": version, **kwargs,
        })

    def list_releases(self, tenant: Optional[str] = None, limit: int = 20) -> list[dict]:
        params: dict[str, Any] = {"limit": limit}
        if tenant:
            params["tenant"] = tenant
        return self._request("GET", "/delivery/releases", params=params)

    def promote_release(self, release_id: str | UUID, environment: str) -> dict:
        return self._request("POST", f"/delivery/releases/{release_id}/promote",
                             params={"environment": environment})

    def create_preview(self, tenant: str, name: str, repository: str, branch: str,
                       pr_number: Optional[int] = None, **kwargs) -> dict:
        data: dict[str, Any] = {"tenant": tenant, "name": name, "repository": repository, "branch": branch}
        if pr_number is not None:
            data["pr_number"] = pr_number
        data.update(kwargs)
        return self._request("POST", "/delivery/previews", json=data)

    def list_previews(self, tenant: Optional[str] = None, repository: Optional[str] = None) -> list[dict]:
        params: dict[str, Any] = {}
        if tenant:
            params["tenant"] = tenant
        if repository:
            params["repository"] = repository
        return self._request("GET", "/delivery/previews", params=params)

    def destroy_preview(self, preview_id: str | UUID) -> dict:
        return self._request("DELETE", f"/delivery/previews/{preview_id}")

    def request_approval(self, requested_by: str, gate_type: str = "manual",
                         pipeline_run_id: Optional[str] = None,
                         deployment_id: Optional[str] = None) -> dict:
        params: dict[str, Any] = {"requested_by": requested_by, "gate_type": gate_type}
        if pipeline_run_id:
            params["pipeline_run_id"] = pipeline_run_id
        if deployment_id:
            params["deployment_id"] = deployment_id
        return self._request("POST", "/delivery/approvals", params=params)

    def approve_decision(self, approval_id: str | UUID, reason: str = "") -> dict:
        return self._request("POST", f"/delivery/approvals/{approval_id}/approve", json={"reason": reason})

    def reject_decision(self, approval_id: str | UUID, reason: str = "") -> dict:
        return self._request("POST", f"/delivery/approvals/{approval_id}/reject", json={"reason": reason})


class AsyncDeliveryMixin:
    """Async delivery operations mixed into AsyncNovaForgeClient."""

    async def create_pipeline(self, tenant: str, project: str, repository: str, branch: str,
                              name: str, **kwargs) -> dict:
        return await self._request("POST", "/delivery/pipelines", json={
            "tenant": tenant, "project": project, "repository": repository,
            "branch": branch, "name": name, **kwargs,
        })

    async def list_pipelines(self, tenant: Optional[str] = None, limit: int = 50) -> list[dict]:
        params: dict[str, Any] = {"limit": limit}
        if tenant:
            params["tenant"] = tenant
        return await self._request("GET", "/delivery/pipelines", params=params)

    async def get_pipeline(self, pipeline_id: str | UUID) -> dict:
        return await self._request("GET", f"/delivery/pipelines/{pipeline_id}")

    async def trigger_pipeline_run(self, pipeline_id: str | UUID, commit_sha: str = "",
                                    actor: str = "sdk") -> dict:
        return await self._request("POST", f"/delivery/pipelines/{pipeline_id}/run", json={
            "commit_sha": commit_sha, "actor": actor,
        })

    async def list_pipeline_runs(self, pipeline_id: str | UUID, limit: int = 20) -> list[dict]:
        return await self._request("GET", f"/delivery/pipelines/{pipeline_id}/runs", params={"limit": limit})

    async def list_jobs(self, run_id: str | UUID) -> list[dict]:
        return await self._request("GET", f"/delivery/runs/{run_id}/jobs")

    async def create_runner(self, name: str, region: str = "default", **kwargs) -> dict:
        return await self._request("POST", "/delivery/runners", json={"name": name, "region": region, **kwargs})

    async def list_runners(self, tenant: Optional[str] = None) -> list[dict]:
        params: dict[str, Any] = {}
        if tenant:
            params["tenant"] = tenant
        return await self._request("GET", "/delivery/runners", params=params)

    async def create_artifact(self, name: str, artifact_type: str, hash_val: str,
                              version: str = "0.0.0", repository: str = "", **kwargs) -> dict:
        return await self._request("POST", "/delivery/artifacts", json={
            "name": name, "artifact_type": artifact_type, "hash": hash_val,
            "version": version, "repository": repository, **kwargs,
        })

    async def create_environment(self, tenant: str, name: str, env_type: str, **kwargs) -> dict:
        return await self._request("POST", "/delivery/environments", json={
            "tenant": tenant, "name": name, "env_type": env_type, **kwargs,
        })

    async def create_deployment(self, environment_id: str | UUID, strategy: str = "rolling",
                                version: str = "0.0.0", **kwargs) -> dict:
        return await self._request("POST", "/delivery/deployments", json={
            "environment_id": str(environment_id), "strategy": strategy,
            "version": version, **kwargs,
        })

    async def start_deployment(self, deployment_id: str | UUID) -> dict:
        return await self._request("POST", f"/delivery/deployments/{deployment_id}/start")

    async def complete_deployment(self, deployment_id: str | UUID, health_status: str = "healthy") -> dict:
        return await self._request("POST", f"/delivery/deployments/{deployment_id}/complete",
                                   params={"health_status": health_status})

    async def create_release(self, tenant: str, project: str, repository: str, version: str, **kwargs) -> dict:
        return await self._request("POST", "/delivery/releases", json={
            "tenant": tenant, "project": project, "repository": repository,
            "version": version, **kwargs,
        })

    async def promote_release(self, release_id: str | UUID, environment: str) -> dict:
        return await self._request("POST", f"/delivery/releases/{release_id}/promote",
                                   params={"environment": environment})

    async def create_preview(self, tenant: str, name: str, repository: str, branch: str,
                             pr_number: Optional[int] = None, **kwargs) -> dict:
        data: dict[str, Any] = {"tenant": tenant, "name": name, "repository": repository, "branch": branch}
        if pr_number is not None:
            data["pr_number"] = pr_number
        data.update(kwargs)
        return await self._request("POST", "/delivery/previews", json=data)

    async def destroy_preview(self, preview_id: str | UUID) -> dict:
        return await self._request("DELETE", f"/delivery/previews/{preview_id}")

    async def approve_deployment(self, deployment_id: str | UUID) -> dict:
        return await self._request("POST", f"/delivery/deployments/{deployment_id}/approve")

    async def rollback_deployment(self, deployment_id: str | UUID, reason: str = "") -> dict:
        return await self._request("POST", f"/delivery/deployments/{deployment_id}/rollback", json={"reason": reason})
