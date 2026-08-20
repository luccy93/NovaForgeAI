"""SDK mixin for the Autonomous Software-Engineering API."""

from typing import Any, Optional

from backend.sdk.client import BaseClient


class AutomationMixin:
    """Sync SDK mixin for automation endpoints."""

    def create_automation_task(self, tenant: str, project: str, repository: str,
                               request: str, actor: str, task_type: str = "feature",
                               autonomy_level: int = 2, **kwargs) -> dict:
        return self.post("/api/v1/automation/tasks", {
            "tenant": tenant, "project": project, "repository": repository,
            "request": request, "actor": actor, "task_type": task_type,
            "autonomy_level": autonomy_level, **kwargs,
        })

    def get_automation_task(self, task_id: str) -> dict:
        return self.get(f"/api/v1/automation/tasks/{task_id}")

    def list_automation_tasks(self, tenant: Optional[str] = None, status: Optional[str] = None,
                               limit: int = 50, offset: int = 0) -> dict:
        params = {"limit": limit, "offset": offset}
        if tenant:
            params["tenant"] = tenant
        if status:
            params["status"] = status
        return self.get("/api/v1/automation/tasks", params=params)

    def run_automation_task(self, task_id: str) -> dict:
        return self.post(f"/api/v1/automation/tasks/{task_id}/run")

    def cancel_automation_task(self, task_id: str) -> dict:
        return self.post(f"/api/v1/automation/tasks/{task_id}/cancel")

    def create_plan(self, task_id: str, objective: str, files: Optional[list] = None, **kwargs) -> dict:
        return self.post(f"/api/v1/automation/tasks/{task_id}/plans", {
            "objective": objective, "files": files or [], **kwargs,
        })

    def get_latest_plan(self, task_id: str) -> dict:
        return self.get(f"/api/v1/automation/tasks/{task_id}/plans/latest")

    def approve_plan(self, plan_id: str) -> dict:
        return self.post(f"/api/v1/automation/plans/{plan_id}/approve")

    def validate_plan(self, plan_id: str) -> dict:
        return self.post(f"/api/v1/automation/plans/{plan_id}/validate")

    def list_patches(self, task_id: str) -> list:
        return self.get(f"/api/v1/automation/tasks/{task_id}/patches")

    def get_patch(self, patch_id: str) -> dict:
        return self.get(f"/api/v1/automation/patches/{patch_id}")

    def validate_patch(self, patch_id: str) -> dict:
        return self.post(f"/api/v1/automation/patches/{patch_id}/validate")

    def get_patch_diff(self, patch_id: str) -> dict:
        return self.get(f"/api/v1/automation/patches/{patch_id}/diff")

    def list_test_runs(self, task_id: str) -> list:
        return self.get(f"/api/v1/automation/tasks/{task_id}/tests")

    def list_reviews(self, task_id: str) -> list:
        return self.get(f"/api/v1/automation/tasks/{task_id}/reviews")

    def list_approvals(self, task_id: str) -> list:
        return self.get(f"/api/v1/automation/tasks/{task_id}/approvals")

    def decide_approval(self, approval_id: str, decision: str, decided_by: str, reason: str = "") -> dict:
        return self.post(f"/api/v1/automation/approvals/{approval_id}/decide", {
            "decision": decision, "decided_by": decided_by, "reason": reason,
        })

    def deploy(self, task_id: str, environment: str = "staging", deployed_by: str = "") -> dict:
        return self.post(f"/api/v1/automation/tasks/{task_id}/deploy", {
            "environment": environment, "deployed_by": deployed_by,
        })

    def list_deployments(self, task_id: str) -> list:
        return self.get(f"/api/v1/automation/tasks/{task_id}/deployments")

    def rollback_deployment(self, deployment_id: str) -> dict:
        return self.post(f"/api/v1/automation/deployments/{deployment_id}/rollback")

    def get_budget(self, tenant: str) -> dict:
        return self.get(f"/api/v1/automation/budgets/{tenant}")

    def update_budget(self, tenant: str, **limits) -> dict:
        return self.put(f"/api/v1/automation/budgets/{tenant}", limits)

    def check_budget(self, tenant: str) -> dict:
        return self.get(f"/api/v1/automation/budgets/{tenant}/check")

    def budget_summary(self, tenant: str) -> dict:
        return self.get(f"/api/v1/automation/budgets/{tenant}/summary")

    def create_template(self, name: str, task_type: str = "feature", steps: Optional[list] = None, **kwargs) -> dict:
        return self.post("/api/v1/automation/templates", {
            "name": name, "task_type": task_type, "steps": steps or [], **kwargs,
        })

    def list_templates(self) -> list:
        return self.get("/api/v1/automation/templates")

    def scan_code(self, diff: str = "", file_changes: Optional[list] = None) -> dict:
        return self.post("/api/v1/automation/security/scan", {
            "diff": diff, "file_changes": file_changes or [],
        })


class AsyncAutomationMixin:
    """Async SDK mixin for automation endpoints."""

    async def create_automation_task(self, tenant: str, project: str, repository: str,
                                      request: str, actor: str, task_type: str = "feature",
                                      autonomy_level: int = 2, **kwargs) -> dict:
        return await self.post("/api/v1/automation/tasks", {
            "tenant": tenant, "project": project, "repository": repository,
            "request": request, "actor": actor, "task_type": task_type,
            "autonomy_level": autonomy_level, **kwargs,
        })

    async def get_automation_task(self, task_id: str) -> dict:
        return await self.get(f"/api/v1/automation/tasks/{task_id}")

    async def list_automation_tasks(self, tenant: Optional[str] = None, status: Optional[str] = None,
                                     limit: int = 50, offset: int = 0) -> dict:
        params = {"limit": limit, "offset": offset}
        if tenant:
            params["tenant"] = tenant
        if status:
            params["status"] = status
        return await self.get("/api/v1/automation/tasks", params=params)

    async def run_automation_task(self, task_id: str) -> dict:
        return await self.post(f"/api/v1/automation/tasks/{task_id}/run")

    async def cancel_automation_task(self, task_id: str) -> dict:
        return await self.post(f"/api/v1/automation/tasks/{task_id}/cancel")

    async def create_plan(self, task_id: str, objective: str, files: Optional[list] = None, **kwargs) -> dict:
        return await self.post(f"/api/v1/automation/tasks/{task_id}/plans", {
            "objective": objective, "files": files or [], **kwargs,
        })

    async def get_latest_plan(self, task_id: str) -> dict:
        return await self.get(f"/api/v1/automation/tasks/{task_id}/plans/latest")

    async def approve_plan(self, plan_id: str) -> dict:
        return await self.post(f"/api/v1/automation/plans/{plan_id}/approve")

    async def validate_plan(self, plan_id: str) -> dict:
        return await self.post(f"/api/v1/automation/plans/{plan_id}/validate")

    async def list_patches(self, task_id: str) -> list:
        return await self.get(f"/api/v1/automation/tasks/{task_id}/patches")

    async def get_patch(self, patch_id: str) -> dict:
        return await self.get(f"/api/v1/automation/patches/{patch_id}")

    async def validate_patch(self, patch_id: str) -> dict:
        return await self.post(f"/api/v1/automation/patches/{patch_id}/validate")

    async def get_patch_diff(self, patch_id: str) -> dict:
        return await self.get(f"/api/v1/automation/patches/{patch_id}/diff")

    async def list_test_runs(self, task_id: str) -> list:
        return await self.get(f"/api/v1/automation/tasks/{task_id}/tests")

    async def list_reviews(self, task_id: str) -> list:
        return await self.get(f"/api/v1/automation/tasks/{task_id}/reviews")

    async def list_approvals(self, task_id: str) -> list:
        return await self.get(f"/api/v1/automation/tasks/{task_id}/approvals")

    async def decide_approval(self, approval_id: str, decision: str, decided_by: str, reason: str = "") -> dict:
        return await self.post(f"/api/v1/automation/approvals/{approval_id}/decide", {
            "decision": decision, "decided_by": decided_by, "reason": reason,
        })

    async def deploy(self, task_id: str, environment: str = "staging", deployed_by: str = "") -> dict:
        return await self.post(f"/api/v1/automation/tasks/{task_id}/deploy", {
            "environment": environment, "deployed_by": deployed_by,
        })

    async def list_deployments(self, task_id: str) -> list:
        return await self.get(f"/api/v1/automation/tasks/{task_id}/deployments")

    async def rollback_deployment(self, deployment_id: str) -> dict:
        return await self.post(f"/api/v1/automation/deployments/{deployment_id}/rollback")

    async def get_budget(self, tenant: str) -> dict:
        return await self.get(f"/api/v1/automation/budgets/{tenant}")

    async def update_budget(self, tenant: str, **limits) -> dict:
        return await self.put(f"/api/v1/automation/budgets/{tenant}", limits)

    async def check_budget(self, tenant: str) -> dict:
        return await self.get(f"/api/v1/automation/budgets/{tenant}/check")

    async def budget_summary(self, tenant: str) -> dict:
        return await self.get(f"/api/v1/automation/budgets/{tenant}/summary")

    async def create_template(self, name: str, task_type: str = "feature", steps: Optional[list] = None, **kwargs) -> dict:
        return await self.post("/api/v1/automation/templates", {
            "name": name, "task_type": task_type, "steps": steps or [], **kwargs,
        })

    async def list_templates(self) -> list:
        return await self.get("/api/v1/automation/templates")

    async def scan_code(self, diff: str = "", file_changes: Optional[list] = None) -> dict:
        return await self.post("/api/v1/automation/security/scan", {
            "diff": diff, "file_changes": file_changes or [],
        })
