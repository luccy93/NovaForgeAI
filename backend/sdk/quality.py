"""AI Software Quality Engine -- SDK (Volume 48)."""

from __future__ import annotations

from typing import Any, Optional


class QualityMixin:
    """Sync SDK methods for the Quality Engine."""

    def quality_create_review(self, tenant: str = "default", repo_id: str = "", review_type: str = "file",
                               target_ref: str = "", mode: str = "standard", **kwargs) -> dict:
        return self._post("/quality/reviews", json={"tenant": tenant, "repo_id": repo_id, "review_type": review_type, "target_ref": target_ref, "mode": mode, **kwargs})

    def quality_list_reviews(self, tenant: str = "default", repo_id: str = "", limit: int = 20) -> list:
        params: dict[str, Any] = {"tenant": tenant, "limit": limit}
        if repo_id:
            params["repo_id"] = repo_id
        return self._get("/quality/reviews", params=params)

    def quality_get_review(self, review_id: str) -> dict:
        return self._get(f"/quality/reviews/{review_id}")

    def quality_analyze(self, review_id: str, mode: str = "standard") -> dict:
        return self._post(f"/quality/reviews/{review_id}/analyze", params={"mode": mode})

    def quality_review_status(self, review_id: str) -> dict:
        return self._get(f"/quality/reviews/{review_id}/status")

    def quality_cancel_review(self, review_id: str) -> dict:
        return self._post(f"/quality/reviews/{review_id}/cancel")

    def quality_get_report(self, review_id: str) -> dict:
        return self._get(f"/quality/reviews/{review_id}/report")

    def quality_get_inline_review(self, review_id: str) -> list:
        return self._get(f"/quality/reviews/{review_id}/inline")

    def quality_get_pr_summary(self, review_id: str) -> dict:
        return self._get(f"/quality/reviews/{review_id}/summary")

    def quality_list_findings(self, review_id: str, severity: str = "", category: str = "", status: str = "") -> list:
        params: dict[str, Any] = {}
        if severity:
            params["severity"] = severity
        if category:
            params["category"] = category
        if status:
            params["status"] = status
        return self._get(f"/quality/reviews/{review_id}/findings", params=params)

    def quality_get_dedup(self, review_id: str) -> list:
        return self._get(f"/quality/reviews/{review_id}/findings/dedup")

    def quality_update_finding(self, review_id: str, finding_idx: int, status: str) -> dict:
        return self._put(f"/quality/reviews/{review_id}/findings/{finding_idx}/status", json={"status": status})

    def quality_submit_feedback(self, review_id: str, finding_idx: int, developer_id: str, action: str, reason: str = "") -> dict:
        return self._post(f"/quality/reviews/{review_id}/findings/{finding_idx}/feedback", json={"developer_id": developer_id, "action": action, "reason": reason})

    def quality_evaluate_gates(self, review_id: str) -> dict:
        return self._post(f"/quality/reviews/{review_id}/gates/evaluate")

    def quality_get_gates(self, review_id: str) -> dict:
        return self._get(f"/quality/reviews/{review_id}/gates")

    def quality_list_baselines(self, tenant: str = "default", repo_id: str = "") -> list:
        params: dict[str, Any] = {"tenant": tenant}
        if repo_id:
            params["repo_id"] = repo_id
        return self._get("/quality/baselines", params=params)

    def quality_create_baseline(self, tenant: str = "default", repo_id: str = "", name: str = "default", description: str = "") -> dict:
        return self._post("/quality/baselines", json={"tenant": tenant, "repo_id": repo_id, "name": name, "description": description})

    def quality_get_baseline(self, name: str, tenant: str = "default", repo_id: str = "") -> dict:
        return self._get(f"/quality/baselines/{name}", params={"tenant": tenant, "repo_id": repo_id})

    def quality_diff_baseline(self, name: str, tenant: str = "default", repo_id: str = "") -> dict:
        return self._get(f"/quality/baselines/{name}/diff", params={"tenant": tenant, "repo_id": repo_id})

    def quality_remediate(self, review_id: str, finding_id: str, patch_diff: str = "") -> dict:
        return self._post(f"/quality/reviews/{review_id}/remediate", json={"finding_id": finding_id, "patch_diff": patch_diff})

    def quality_verify_remediation(self, review_id: str, remediation_id: str) -> dict:
        return self._post(f"/quality/reviews/{review_id}/remediate/verify", params={"remediation_id": remediation_id})

    def quality_generate_tests(self, review_id: str) -> dict:
        return self._post(f"/quality/reviews/{review_id}/generate-tests")

    def quality_history(self, repo_id: str, tenant: str = "default") -> dict:
        return self._get(f"/quality/history/{repo_id}", params={"tenant": tenant})

    def quality_trends(self, repo_id: str, tenant: str = "default") -> dict:
        return self._get(f"/quality/history/{repo_id}/trends", params={"tenant": tenant})

    def quality_hotspots(self, repo_id: str, tenant: str = "default") -> list:
        return self._get(f"/quality/history/{repo_id}/hotspots", params={"tenant": tenant})

    def quality_analyze_file(self, file_path: str, content: str, tenant: str = "default", mode: str = "standard") -> dict:
        return self._post("/quality/analyze/file", json={"file_path": file_path, "content": content, "tenant": tenant, "mode": mode})

    def quality_analyze_pr(self, repo_id: str, pr_number: int, tenant: str = "default", mode: str = "standard") -> dict:
        return self._post("/quality/analyze/pr", json={"repo_id": repo_id, "pr_number": pr_number, "tenant": tenant, "mode": mode})

    def quality_analyze_commit(self, repo_id: str, commit_sha: str, tenant: str = "default", mode: str = "standard") -> dict:
        return self._post("/quality/analyze/commit", json={"repo_id": repo_id, "commit_sha": commit_sha, "tenant": tenant, "mode": mode})

    def quality_analyze_branch(self, repo_id: str, branch: str, tenant: str = "default", mode: str = "standard") -> dict:
        return self._post("/quality/analyze/branch", json={"repo_id": repo_id, "branch": branch, "tenant": tenant, "mode": mode})

    def quality_analyze_release(self, repo_id: str, release_tag: str, tenant: str = "default", mode: str = "release") -> dict:
        return self._post("/quality/analyze/release", json={"repo_id": repo_id, "release_tag": release_tag, "tenant": tenant, "mode": mode})


class AsyncQualityMixin:
    """Async SDK methods for the Quality Engine."""

    async def quality_create_review(self, tenant: str = "default", repo_id: str = "", review_type: str = "file",
                                     target_ref: str = "", mode: str = "standard", **kwargs) -> dict:
        return await self._apost("/quality/reviews", json={"tenant": tenant, "repo_id": repo_id, "review_type": review_type, "target_ref": target_ref, "mode": mode, **kwargs})

    async def quality_list_reviews(self, tenant: str = "default", repo_id: str = "", limit: int = 20) -> list:
        params: dict[str, Any] = {"tenant": tenant, "limit": limit}
        if repo_id:
            params["repo_id"] = repo_id
        return await self._aget("/quality/reviews", params=params)

    async def quality_get_review(self, review_id: str) -> dict:
        return await self._aget(f"/quality/reviews/{review_id}")

    async def quality_analyze(self, review_id: str, mode: str = "standard") -> dict:
        return await self._apost(f"/quality/reviews/{review_id}/analyze", params={"mode": mode})

    async def quality_review_status(self, review_id: str) -> dict:
        return await self._aget(f"/quality/reviews/{review_id}/status")

    async def quality_cancel_review(self, review_id: str) -> dict:
        return await self._apost(f"/quality/reviews/{review_id}/cancel")

    async def quality_get_report(self, review_id: str) -> dict:
        return await self._aget(f"/quality/reviews/{review_id}/report")

    async def quality_get_inline_review(self, review_id: str) -> list:
        return await self._aget(f"/quality/reviews/{review_id}/inline")

    async def quality_get_pr_summary(self, review_id: str) -> dict:
        return await self._aget(f"/quality/reviews/{review_id}/summary")

    async def quality_list_findings(self, review_id: str, severity: str = "", category: str = "", status: str = "") -> list:
        params: dict[str, Any] = {}
        if severity:
            params["severity"] = severity
        if category:
            params["category"] = category
        if status:
            params["status"] = status
        return await self._aget(f"/quality/reviews/{review_id}/findings", params=params)

    async def quality_get_dedup(self, review_id: str) -> list:
        return await self._aget(f"/quality/reviews/{review_id}/findings/dedup")

    async def quality_update_finding(self, review_id: str, finding_idx: int, status: str) -> dict:
        return await self._aput(f"/quality/reviews/{review_id}/findings/{finding_idx}/status", json={"status": status})

    async def quality_evaluate_gates(self, review_id: str) -> dict:
        return await self._apost(f"/quality/reviews/{review_id}/gates/evaluate")

    async def quality_list_baselines(self, tenant: str = "default", repo_id: str = "") -> list:
        params: dict[str, Any] = {"tenant": tenant}
        if repo_id:
            params["repo_id"] = repo_id
        return await self._aget("/quality/baselines", params=params)

    async def quality_create_baseline(self, tenant: str = "default", repo_id: str = "", name: str = "default", description: str = "") -> dict:
        return await self._apost("/quality/baselines", json={"tenant": tenant, "repo_id": repo_id, "name": name, "description": description})

    async def quality_analyze_file(self, file_path: str, content: str, tenant: str = "default", mode: str = "standard") -> dict:
        return await self._apost("/quality/analyze/file", json={"file_path": file_path, "content": content, "tenant": tenant, "mode": mode})

    async def quality_analyze_pr(self, repo_id: str, pr_number: int, tenant: str = "default", mode: str = "standard") -> dict:
        return await self._apost("/quality/analyze/pr", json={"repo_id": repo_id, "pr_number": pr_number, "tenant": tenant, "mode": mode})

    async def quality_history(self, repo_id: str, tenant: str = "default") -> dict:
        return await self._aget(f"/quality/history/{repo_id}", params={"tenant": tenant})

    async def quality_trends(self, repo_id: str, tenant: str = "default") -> dict:
        return await self._aget(f"/quality/history/{repo_id}/trends", params={"tenant": tenant})

    async def quality_hotspots(self, repo_id: str, tenant: str = "default") -> list:
        return await self._aget(f"/quality/history/{repo_id}/hotspots", params={"tenant": tenant})
