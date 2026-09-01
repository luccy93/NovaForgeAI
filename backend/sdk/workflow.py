"""Workflow SDK mixin — Volume 66."""

from typing import Any, Dict, Optional


class WorkflowMixin:
    """Synchronous Workflow mixin."""

    def wf_create(self, name: str, **kwargs: Any) -> dict:
        payload: Dict[str, Any] = {"name": name}
        for k in ("description", "workspace", "version", "definition", "inputs", "outputs", "owner"):
            if k in kwargs and kwargs[k] is not None:
                payload[k] = kwargs[k]
        return self.post(self._build_url("/workflows"), data=payload)

    def wf_list(self, limit: int = 20, **kwargs: Any) -> dict:
        params: Dict[str, Any] = {"limit": limit}
        for k in ("status",):
            if k in kwargs and kwargs[k] is not None:
                params[k] = kwargs[k]
        return self.get(self._build_url("/workflows"), params=params)

    def wf_get(self, workflow_id: str) -> dict:
        return self.get(self._build_url(f"/workflows/{workflow_id}"))

    def wf_publish(self, workflow_id: str, version_id: str | None = None) -> dict:
        payload: Dict[str, Any] = {}
        if version_id:
            payload["version_id"] = version_id
        return self.post(self._build_url(f"/workflows/{workflow_id}/publish"), data=payload)

    def wf_create_version(self, workflow_id: str, definition: dict) -> dict:
        return self.post(self._build_url(f"/workflows/{workflow_id}/versions"), data={"definition": definition})

    def wf_run(self, workflow_id: str, inputs: dict | None = None, idempotency_key: str | None = None, region: str | None = None) -> dict:
        payload: Dict[str, Any] = {"inputs": inputs or {}}
        if idempotency_key:
            payload["idempotency_key"] = idempotency_key
        if region:
            payload["region"] = region
        return self.post(self._build_url(f"/workflows/{workflow_id}/trigger"), data=payload)

    def wf_status(self, run_id: str) -> dict:
        return self.get(self._build_url(f"/workflows/runs/{run_id}"))

    def wf_pause(self, run_id: str) -> dict:
        return self.post(self._build_url(f"/workflows/runs/{run_id}/pause"), data={})

    def wf_resume(self, run_id: str) -> dict:
        return self.post(self._build_url(f"/workflows/runs/{run_id}/resume"), data={})

    def wf_cancel(self, run_id: str) -> dict:
        return self.post(self._build_url(f"/workflows/runs/{run_id}/cancel"), data={})

    def wf_list_approvals(self, limit: int = 20) -> dict:
        return self.get(self._build_url("/workflows/approvals"), params={"limit": limit})

    def wf_approve(self, approval_id: str, decision: str = "APPROVED", binding_hash: str | None = None) -> dict:
        payload: Dict[str, Any] = {"decision": decision}
        if binding_hash:
            payload["binding_hash"] = binding_hash
        return self.post(self._build_url(f"/workflows/approvals/{approval_id}/decide"), data=payload)

    # Commit 2 additions
    def wf_templates(self, limit: int = 20) -> dict:
        return self.get(self._build_url("/workflows/templates"), params={"limit": limit})

    def wf_create_template(self, name: str, definition: dict, **kwargs: Any) -> dict:
        payload: Dict[str, Any] = {"name": name, "definition": definition}
        for k in ("description", "category", "version"):
            if k in kwargs and kwargs[k] is not None:
                payload[k] = kwargs[k]
        return self.post(self._build_url("/workflows/templates"), data=payload)

    def wf_replay(self, run_id: str) -> dict:
        return self.post(self._build_url(f"/workflows/runs/{run_id}/replay"), data={})

    def wf_recover(self, run_id: str, worker_id: str | None = None) -> dict:
        payload: Dict[str, Any] = {}
        if worker_id:
            payload["worker_id"] = worker_id
        return self.post(self._build_url(f"/workflows/runs/{run_id}/recover"), data=payload)

    def wf_tasks(self, status: str | None = None, limit: int = 20) -> dict:
        params: Dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        return self.get(self._build_url("/workflows/human-tasks"), params=params)

    def wf_complete_task(self, task_id: str, decision: str = "COMPLETED", comment: str | None = None) -> dict:
        payload: Dict[str, Any] = {"decision": decision}
        if comment:
            payload["comment"] = comment
        return self.post(self._build_url(f"/workflows/human-tasks/{task_id}/complete"), data=payload)

    def wf_sla(self, run_id: str) -> dict:
        return self.get(self._build_url(f"/workflows/sla/{run_id}"))

    def wf_health(self) -> dict:
        return self.get(self._build_url("/workflows/health"))

    def wf_anomalies(self, limit: int = 20) -> dict:
        return self.get(self._build_url("/workflows/anomalies"), params={"limit": limit})


class AsyncWorkflowMixin:
    """Async Workflow mixin."""

    async def wf_create(self, name: str, **kwargs: Any) -> dict:
        payload: Dict[str, Any] = {"name": name}
        for k in ("description", "workspace", "version", "definition", "inputs", "outputs", "owner"):
            if k in kwargs and kwargs[k] is not None:
                payload[k] = kwargs[k]
        return await self.post(self._build_url("/workflows"), data=payload)

    async def wf_list(self, limit: int = 20, **kwargs: Any) -> dict:
        params: Dict[str, Any] = {"limit": limit}
        for k in ("status",):
            if k in kwargs and kwargs[k] is not None:
                params[k] = kwargs[k]
        return await self.get(self._build_url("/workflows"), params=params)

    async def wf_get(self, workflow_id: str) -> dict:
        return await self.get(self._build_url(f"/workflows/{workflow_id}"))

    async def wf_publish(self, workflow_id: str, version_id: str | None = None) -> dict:
        payload: Dict[str, Any] = {}
        if version_id:
            payload["version_id"] = version_id
        return await self.post(self._build_url(f"/workflows/{workflow_id}/publish"), data=payload)

    async def wf_create_version(self, workflow_id: str, definition: dict) -> dict:
        return await self.post(self._build_url(f"/workflows/{workflow_id}/versions"), data={"definition": definition})

    async def wf_run(self, workflow_id: str, inputs: dict | None = None, idempotency_key: str | None = None, region: str | None = None) -> dict:
        payload: Dict[str, Any] = {"inputs": inputs or {}}
        if idempotency_key:
            payload["idempotency_key"] = idempotency_key
        if region:
            payload["region"] = region
        return await self.post(self._build_url(f"/workflows/{workflow_id}/trigger"), data=payload)

    async def wf_status(self, run_id: str) -> dict:
        return await self.get(self._build_url(f"/workflows/runs/{run_id}"))

    async def wf_pause(self, run_id: str) -> dict:
        return await self.post(self._build_url(f"/workflows/runs/{run_id}/pause"), data={})

    async def wf_resume(self, run_id: str) -> dict:
        return await self.post(self._build_url(f"/workflows/runs/{run_id}/resume"), data={})

    async def wf_cancel(self, run_id: str) -> dict:
        return await self.post(self._build_url(f"/workflows/runs/{run_id}/cancel"), data={})

    async def wf_list_approvals(self, limit: int = 20) -> dict:
        return await self.get(self._build_url("/workflows/approvals"), params={"limit": limit})

    async def wf_approve(self, approval_id: str, decision: str = "APPROVED", binding_hash: str | None = None) -> dict:
        payload: Dict[str, Any] = {"decision": decision}
        if binding_hash:
            payload["binding_hash"] = binding_hash
        return await self.post(self._build_url(f"/workflows/approvals/{approval_id}/decide"), data=payload)

    async def wf_templates(self, limit: int = 20) -> dict:
        return await self.get(self._build_url("/workflows/templates"), params={"limit": limit})

    async def wf_create_template(self, name: str, definition: dict, **kwargs: Any) -> dict:
        payload: Dict[str, Any] = {"name": name, "definition": definition}
        for k in ("description", "category", "version"):
            if k in kwargs and kwargs[k] is not None:
                payload[k] = kwargs[k]
        return await self.post(self._build_url("/workflows/templates"), data=payload)

    async def wf_replay(self, run_id: str) -> dict:
        return await self.post(self._build_url(f"/workflows/runs/{run_id}/replay"), data={})

    async def wf_recover(self, run_id: str, worker_id: str | None = None) -> dict:
        payload: Dict[str, Any] = {}
        if worker_id:
            payload["worker_id"] = worker_id
        return await self.post(self._build_url(f"/workflows/runs/{run_id}/recover"), data=payload)

    async def wf_tasks(self, status: str | None = None, limit: int = 20) -> dict:
        params: Dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        return await self.get(self._build_url("/workflows/human-tasks"), params=params)

    async def wf_complete_task(self, task_id: str, decision: str = "COMPLETED", comment: str | None = None) -> dict:
        payload: Dict[str, Any] = {"decision": decision}
        if comment:
            payload["comment"] = comment
        return await self.post(self._build_url(f"/workflows/human-tasks/{task_id}/complete"), data=payload)

    async def wf_sla(self, run_id: str) -> dict:
        return await self.get(self._build_url(f"/workflows/sla/{run_id}"))

    async def wf_health(self) -> dict:
        return await self.get(self._build_url("/workflows/health"))

    async def wf_anomalies(self, limit: int = 20) -> dict:
        return await self.get(self._build_url("/workflows/anomalies"), params={"limit": limit})
