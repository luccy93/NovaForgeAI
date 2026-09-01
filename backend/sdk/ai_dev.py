"""AI Developer Experience SDK mixin — Volume 67."""

from typing import Any, Dict, Optional


class AIDevMixin:
    """Synchronous AI Developer Experience mixin (namespace /api/v1/ai-dev)."""

    def ai_workspace_create(
        self, name: str, repository_id: str, branch: str = "main",
        commit_sha: str | None = None, description: str | None = None,
        pinned: bool = False, classification: str = "INTERNAL",
    ) -> dict:
        payload: Dict[str, Any] = {
            "name": name,
            "repository_id": repository_id,
            "branch": branch,
            "pinned": pinned,
            "classification": classification,
        }
        if commit_sha:
            payload["commit_sha"] = commit_sha
        if description:
            payload["description"] = description
        return self.post(self._build_url("/ai-dev/workspaces"), data=payload)

    def ai_workspaces(self, limit: int = 50, repository_id: str | None = None) -> dict:
        params: Dict[str, Any] = {"limit": limit}
        if repository_id:
            params["repository_id"] = repository_id
        return self.get(self._build_url("/ai-dev/workspaces"), params=params)

    def ai_workspace_get(self, workspace_id: str) -> dict:
        return self.get(self._build_url(f"/ai-dev/workspaces/{workspace_id}"))

    def ai_index_overview(self, repository_id: str) -> dict:
        return self.get(self._build_url(f"/ai-dev/repositories/{repository_id}/index"))

    def ai_index_record(self, repository_id: str, branch: str = "main", commit_sha: str | None = None) -> dict:
        payload: Dict[str, Any] = {"branch": branch}
        if commit_sha:
            payload["commit_sha"] = commit_sha
        return self.post(self._build_url(f"/ai-dev/repositories/{repository_id}/index"), data=payload)

    def ai_search(self, repository_id: str, query: str, symbol_type: str | None = None, limit: int = 12) -> dict:
        params: Dict[str, Any] = {"q": query, "limit": limit}
        if symbol_type:
            params["symbol_type"] = symbol_type
        return self.get(self._build_url(f"/ai-dev/repositories/{repository_id}/search"), params=params)

    def ai_symbols(self, repository_id: str, q: str, symbol_type: str | None = None, limit: int = 20) -> dict:
        params: Dict[str, Any] = {"q": q, "limit": limit}
        if symbol_type:
            params["symbol_type"] = symbol_type
        return self.get(self._build_url(f"/ai-dev/repositories/{repository_id}/symbols"), params=params)

    def ai_context(self, repository_id: str, q: str, token_budget: int = 4000) -> dict:
        return self.get(
            self._build_url(f"/ai-dev/repositories/{repository_id}/context"),
            params={"q": q, "token_budget": token_budget},
        )

    def ai_chat(self, repository_id: str, question: str, workspace_id: str | None = None, model_hint: str | None = None) -> dict:
        payload: Dict[str, Any] = {"repository_id": repository_id, "question": question}
        if workspace_id:
            payload["workspace_id"] = workspace_id
        if model_hint:
            payload["model_hint"] = model_hint
        return self.post(self._build_url("/ai-dev/chat"), data=payload)

    def ai_explain(self, repository_id: str, kind: str, target: str, top: int = 20) -> dict:
        return self.post(
            self._build_url("/ai-dev/explain"),
            data={"repository_id": repository_id, "kind": kind, "target": target, "top": top},
        )

    def ai_patch_create(
        self, repository_id: str, title: str, files: list[dict],
        branch: str | None = None, base_commit_sha: str | None = None,
        workspace_id: str | None = None, model: str | None = None, source: str = "ai",
    ) -> dict:
        payload: Dict[str, Any] = {"repository_id": repository_id, "title": title, "files": files}
        if branch:
            payload["branch"] = branch
        if base_commit_sha:
            payload["base_commit_sha"] = base_commit_sha
        if workspace_id:
            payload["workspace_id"] = workspace_id
        if model:
            payload["model"] = model
        payload["source"] = source
        return self.post(self._build_url("/ai-dev/patch"), data=payload)

    def ai_patch_get(self, patch_id: str) -> dict:
        return self.get(self._build_url(f"/ai-dev/patches/{patch_id}"))

    def ai_patch_apply(self, patch_id: str, current_files: dict | None = None) -> dict:
        payload: Dict[str, Any] = {}
        if current_files:
            payload["current_files"] = current_files
        return self.post(self._build_url(f"/ai-dev/patches/{patch_id}/apply"), data=payload)

    def ai_patch_rollback(self, patch_id: str) -> dict:
        return self.post(self._build_url(f"/ai-dev/patches/{patch_id}/rollback"), data={})

    def ai_review_create(
        self, repository_id: str, files: list[dict],
        branch: str | None = None, commit_sha: str | None = None,
        patch_id: str | None = None, workspace_id: str | None = None,
        rules_version: str = "1.0",
    ) -> dict:
        payload: Dict[str, Any] = {"repository_id": repository_id, "files": files}
        if branch:
            payload["branch"] = branch
        if commit_sha:
            payload["commit_sha"] = commit_sha
        if patch_id:
            payload["patch_id"] = patch_id
        if workspace_id:
            payload["workspace_id"] = workspace_id
        payload["rules_version"] = rules_version
        return self.post(self._build_url("/ai-dev/review"), data=payload)

    def ai_review_get(self, review_id: str) -> dict:
        return self.get(self._build_url(f"/ai-dev/reviews/{review_id}"))

    def ai_review_dismiss(self, review_id: str, finding_id: str, reason: str | None = None) -> dict:
        payload: Dict[str, Any] = {}
        if reason:
            payload["reason"] = reason
        return self.post(
            self._build_url(f"/ai-dev/reviews/{review_id}/findings/{finding_id}/dismiss"),
            data=payload,
        )

    def ai_tests_generate(
        self, repository_id: str, patch_id: str | None = None,
        commit_sha: str | None = None, branch: str | None = None, framework: str | None = None,
    ) -> dict:
        payload: Dict[str, Any] = {"repository_id": repository_id}
        if patch_id:
            payload["patch_id"] = patch_id
        if commit_sha:
            payload["commit_sha"] = commit_sha
        if branch:
            payload["branch"] = branch
        if framework:
            payload["framework"] = framework
        return self.post(self._build_url("/ai-dev/tests/generate"), data=payload)

    def ai_tests_execute(self, run_id: str) -> dict:
        return self.post(self._build_url(f"/ai-dev/tests/{run_id}/execute"), data={})

    def ai_tests_result(
        self, run_id: str, status: str, results: list | None = None,
        logs: str | None = None, failures_analysis: str | None = None,
        duration_ms: int | None = None,
    ) -> dict:
        payload: Dict[str, Any] = {"status": status}
        if results is not None:
            payload["results"] = results
        if logs is not None:
            payload["logs"] = logs
        if failures_analysis is not None:
            payload["failures_analysis"] = failures_analysis
        if duration_ms is not None:
            payload["duration_ms"] = duration_ms
        return self.post(self._build_url(f"/ai-dev/tests/{run_id}/result"), data=payload)

    def ai_fix(
        self, repository_id: str, files: list[dict], goal: str,
        patch_title: str, branch: str | None = None, model: str | None = None,
        max_iterations: int = 3,
    ) -> dict:
        payload: Dict[str, Any] = {
            "repository_id": repository_id,
            "files": files,
            "goal": goal,
            "patch_title": patch_title,
            "max_iterations": max_iterations,
        }
        if branch:
            payload["branch"] = branch
        if model:
            payload["model"] = model
        return self.post(self._build_url("/ai-dev/fix"), data=payload)

    def ai_dependencies(self, repository_id: str, limit: int = 200) -> dict:
        return self.get(
            self._build_url(f"/ai-dev/repositories/{repository_id}/dependencies"),
            params={"limit": limit},
        )

    def ai_dependencies_scan(self, repository_id: str, files: list[dict] | None = None) -> dict:
        payload: Dict[str, Any] = {}
        if files:
            payload["files"] = files
        return self.post(
            self._build_url(f"/ai-dev/repositories/{repository_id}/dependencies/scan"),
            data=payload,
        )

    def ai_builds(self, repository_id: str, commit_sha: str | None = None) -> dict:
        params: Dict[str, Any] = {}
        if commit_sha:
            params["commit_sha"] = commit_sha
        return self.get(
            self._build_url(f"/ai-dev/repositories/{repository_id}/builds"), params=params
        )

    def ai_change_summary(self, repository_id: str, commit_sha: str | None = None, files: list[dict] | None = None) -> dict:
        payload: Dict[str, Any] = {"repository_id": repository_id}
        if commit_sha:
            payload["commit_sha"] = commit_sha
        if files:
            payload["files"] = files
        return self.post(self._build_url("/ai-dev/changes/summary"), data=payload)

    def ai_pr_assist(self, repository_id: str, title: str, files: list[dict], commit_sha: str | None = None, test_summary: dict | None = None, findings: list[dict] | None = None) -> dict:
        payload: Dict[str, Any] = {"repository_id": repository_id, "title": title, "files": files}
        if commit_sha:
            payload["commit_sha"] = commit_sha
        if test_summary:
            payload["test_summary"] = test_summary
        if findings:
            payload["findings"] = findings
        return self.post(self._build_url("/ai-dev/changes/pr-assist"), data=payload)

    def ai_usage(self, action: str | None = None, limit: int = 50) -> dict:
        params: Dict[str, Any] = {"limit": limit}
        if action:
            params["action"] = action
        return self.get(self._build_url("/ai-dev/usage"), params=params)


class AsyncAIDevMixin:
    """Async AI Developer Experience mixin."""

    async def ai_workspace_create(self, name: str, repository_id: str, branch: str = "main",
                                  commit_sha: str | None = None, description: str | None = None,
                                  pinned: bool = False, classification: str = "INTERNAL") -> dict:
        payload: Dict[str, Any] = {
            "name": name, "repository_id": repository_id, "branch": branch,
            "pinned": pinned, "classification": classification,
        }
        if commit_sha:
            payload["commit_sha"] = commit_sha
        if description:
            payload["description"] = description
        return await self.post(self._build_url("/ai-dev/workspaces"), data=payload)

    async def ai_workspaces(self, limit: int = 50, repository_id: str | None = None) -> dict:
        params: Dict[str, Any] = {"limit": limit}
        if repository_id:
            params["repository_id"] = repository_id
        return await self.get(self._build_url("/ai-dev/workspaces"), params=params)

    async def ai_workspace_get(self, workspace_id: str) -> dict:
        return await self.get(self._build_url(f"/ai-dev/workspaces/{workspace_id}"))

    async def ai_index_overview(self, repository_id: str) -> dict:
        return await self.get(self._build_url(f"/ai-dev/repositories/{repository_id}/index"))

    async def ai_index_record(self, repository_id: str, branch: str = "main", commit_sha: str | None = None) -> dict:
        payload: Dict[str, Any] = {"branch": branch}
        if commit_sha:
            payload["commit_sha"] = commit_sha
        return await self.post(self._build_url(f"/ai-dev/repositories/{repository_id}/index"), data=payload)

    async def ai_search(self, repository_id: str, query: str, symbol_type: str | None = None, limit: int = 12) -> dict:
        params: Dict[str, Any] = {"q": query, "limit": limit}
        if symbol_type:
            params["symbol_type"] = symbol_type
        return await self.get(self._build_url(f"/ai-dev/repositories/{repository_id}/search"), params=params)

    async def ai_symbols(self, repository_id: str, q: str, symbol_type: str | None = None, limit: int = 20) -> dict:
        params: Dict[str, Any] = {"q": q, "limit": limit}
        if symbol_type:
            params["symbol_type"] = symbol_type
        return await self.get(self._build_url(f"/ai-dev/repositories/{repository_id}/symbols"), params=params)

    async def ai_context(self, repository_id: str, q: str, token_budget: int = 4000) -> dict:
        return await self.get(
            self._build_url(f"/ai-dev/repositories/{repository_id}/context"),
            params={"q": q, "token_budget": token_budget},
        )

    async def ai_chat(self, repository_id: str, question: str, workspace_id: str | None = None, model_hint: str | None = None) -> dict:
        payload: Dict[str, Any] = {"repository_id": repository_id, "question": question}
        if workspace_id:
            payload["workspace_id"] = workspace_id
        if model_hint:
            payload["model_hint"] = model_hint
        return await self.post(self._build_url("/ai-dev/chat"), data=payload)

    async def ai_explain(self, repository_id: str, kind: str, target: str, top: int = 20) -> dict:
        return await self.post(
            self._build_url("/ai-dev/explain"),
            data={"repository_id": repository_id, "kind": kind, "target": target, "top": top},
        )

    async def ai_patch_create(self, repository_id: str, title: str, files: list[dict],
                              branch: str | None = None, base_commit_sha: str | None = None,
                              workspace_id: str | None = None, model: str | None = None,
                              source: str = "ai") -> dict:
        payload: Dict[str, Any] = {"repository_id": repository_id, "title": title, "files": files}
        if branch:
            payload["branch"] = branch
        if base_commit_sha:
            payload["base_commit_sha"] = base_commit_sha
        if workspace_id:
            payload["workspace_id"] = workspace_id
        if model:
            payload["model"] = model
        payload["source"] = source
        return await self.post(self._build_url("/ai-dev/patch"), data=payload)

    async def ai_patch_get(self, patch_id: str) -> dict:
        return await self.get(self._build_url(f"/ai-dev/patches/{patch_id}"))

    async def ai_patch_apply(self, patch_id: str, current_files: dict | None = None) -> dict:
        payload: Dict[str, Any] = {}
        if current_files:
            payload["current_files"] = current_files
        return await self.post(self._build_url(f"/ai-dev/patches/{patch_id}/apply"), data=payload)

    async def ai_patch_rollback(self, patch_id: str) -> dict:
        return await self.post(self._build_url(f"/ai-dev/patches/{patch_id}/rollback"), data={})

    async def ai_review_create(self, repository_id: str, files: list[dict],
                               branch: str | None = None, commit_sha: str | None = None,
                               patch_id: str | None = None, workspace_id: str | None = None,
                               rules_version: str = "1.0") -> dict:
        payload: Dict[str, Any] = {"repository_id": repository_id, "files": files}
        if branch:
            payload["branch"] = branch
        if commit_sha:
            payload["commit_sha"] = commit_sha
        if patch_id:
            payload["patch_id"] = patch_id
        if workspace_id:
            payload["workspace_id"] = workspace_id
        payload["rules_version"] = rules_version
        return await self.post(self._build_url("/ai-dev/review"), data=payload)

    async def ai_review_get(self, review_id: str) -> dict:
        return await self.get(self._build_url(f"/ai-dev/reviews/{review_id}"))

    async def ai_review_dismiss(self, review_id: str, finding_id: str, reason: str | None = None) -> dict:
        payload: Dict[str, Any] = {}
        if reason:
            payload["reason"] = reason
        return await self.post(
            self._build_url(f"/ai-dev/reviews/{review_id}/findings/{finding_id}/dismiss"),
            data=payload,
        )

    async def ai_tests_generate(self, repository_id: str, patch_id: str | None = None,
                                commit_sha: str | None = None, branch: str | None = None,
                                framework: str | None = None) -> dict:
        payload: Dict[str, Any] = {"repository_id": repository_id}
        if patch_id:
            payload["patch_id"] = patch_id
        if commit_sha:
            payload["commit_sha"] = commit_sha
        if branch:
            payload["branch"] = branch
        if framework:
            payload["framework"] = framework
        return await self.post(self._build_url("/ai-dev/tests/generate"), data=payload)

    async def ai_tests_execute(self, run_id: str) -> dict:
        return await self.post(self._build_url(f"/ai-dev/tests/{run_id}/execute"), data={})

    async def ai_tests_result(self, run_id: str, status: str, results: list | None = None,
                              logs: str | None = None, failures_analysis: str | None = None,
                              duration_ms: int | None = None) -> dict:
        payload: Dict[str, Any] = {"status": status}
        if results is not None:
            payload["results"] = results
        if logs is not None:
            payload["logs"] = logs
        if failures_analysis is not None:
            payload["failures_analysis"] = failures_analysis
        if duration_ms is not None:
            payload["duration_ms"] = duration_ms
        return await self.post(self._build_url(f"/ai-dev/tests/{run_id}/result"), data=payload)

    async def ai_fix(self, repository_id: str, files: list[dict], goal: str,
                     patch_title: str, branch: str | None = None, model: str | None = None,
                     max_iterations: int = 3) -> dict:
        payload: Dict[str, Any] = {
            "repository_id": repository_id, "files": files, "goal": goal,
            "patch_title": patch_title, "max_iterations": max_iterations,
        }
        if branch:
            payload["branch"] = branch
        if model:
            payload["model"] = model
        return await self.post(self._build_url("/ai-dev/fix"), data=payload)

    async def ai_dependencies(self, repository_id: str, limit: int = 200) -> dict:
        return await self.get(
            self._build_url(f"/ai-dev/repositories/{repository_id}/dependencies"),
            params={"limit": limit},
        )

    async def ai_dependencies_scan(self, repository_id: str, files: list[dict] | None = None) -> dict:
        payload: Dict[str, Any] = {}
        if files:
            payload["files"] = files
        return await self.post(
            self._build_url(f"/ai-dev/repositories/{repository_id}/dependencies/scan"),
            data=payload,
        )

    async def ai_builds(self, repository_id: str, commit_sha: str | None = None) -> dict:
        params: Dict[str, Any] = {}
        if commit_sha:
            params["commit_sha"] = commit_sha
        return await self.get(
            self._build_url(f"/ai-dev/repositories/{repository_id}/builds"), params=params
        )

    async def ai_change_summary(self, repository_id: str, commit_sha: str | None = None, files: list[dict] | None = None) -> dict:
        payload: Dict[str, Any] = {"repository_id": repository_id}
        if commit_sha:
            payload["commit_sha"] = commit_sha
        if files:
            payload["files"] = files
        return await self.post(self._build_url("/ai-dev/changes/summary"), data=payload)

    async def ai_pr_assist(self, repository_id: str, title: str, files: list[dict], commit_sha: str | None = None, test_summary: dict | None = None, findings: list[dict] | None = None) -> dict:
        payload: Dict[str, Any] = {"repository_id": repository_id, "title": title, "files": files}
        if commit_sha:
            payload["commit_sha"] = commit_sha
        if test_summary:
            payload["test_summary"] = test_summary
        if findings:
            payload["findings"] = findings
        return await self.post(self._build_url("/ai-dev/changes/pr-assist"), data=payload)

    async def ai_usage(self, action: str | None = None, limit: int = 50) -> dict:
        params: Dict[str, Any] = {"limit": limit}
        if action:
            params["action"] = action
        return await self.get(self._build_url("/ai-dev/usage"), params=params)