"""Governance SDK mixin — Volume 71 Commit 1."""

from typing import Any, Dict, Optional


class GovernanceMixin:
    def governance_list_policies(self, status: str = "", limit: int = 100) -> dict:
        params: Dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        return self.get(self._build_url("/governance/policies"), params=params)

    def governance_create_policy(self, name: str, **fields: Any) -> dict:
        return self.post(self._build_url("/governance/policies"), data={"name": name, **fields})

    def governance_get_policy(self, policy_id: str) -> dict:
        return self.get(self._build_url(f"/governance/policies/{policy_id}"))

    def governance_create_version(self, policy_id: str, rules: list, **fields: Any) -> dict:
        return self.post(self._build_url(f"/governance/policies/{policy_id}/versions"),
                         data={"rules": rules, **fields})

    def governance_set_version_status(self, version_id: str, status: str, reason: str = "") -> dict:
        return self.post(self._build_url(f"/governance/versions/{version_id}/status"),
                         data={"status": status, "reason": reason})

    def governance_create_binding(self, policy_id: str, version_id: str, scope_type: str, **fields: Any) -> dict:
        return self.post(self._build_url("/governance/bindings"),
                         data={"policy_id": policy_id, "version_id": version_id,
                               "scope_type": scope_type, **fields})

    def governance_evaluate(self, scope_type: str, **fields: Any) -> dict:
        return self.post(self._build_url("/governance/evaluate"),
                         data={"scope_type": scope_type, **fields})

    def governance_simulate(self, **fields: Any) -> dict:
        return self.post(self._build_url("/governance/simulate"), data=fields)

    def governance_list_decisions(self, limit: int = 100) -> dict:
        return self.get(self._build_url("/governance/decisions"), params={"limit": limit})

    def governance_create_exception(self, policy_id: str, justification: str, **fields: Any) -> dict:
        return self.post(self._build_url("/governance/policy-exceptions"),
                         data={"policy_id": policy_id, "justification": justification, **fields})

    def governance_approve_exception(self, exception_id: str, approver: str, **fields: Any) -> dict:
        return self.post(self._build_url(f"/governance/policy-exceptions/{exception_id}/approve"),
                         data={"approver": approver, **fields})

    def governance_posture(self, scope_type: str = "tenant") -> dict:
        return self.get(self._build_url("/governance/posture"), params={"scope_type": scope_type})


class AsyncGovernanceMixin:
    async def governance_list_policies(self, status: str = "", limit: int = 100) -> dict:
        params: Dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        return await self.get(self._build_url("/governance/policies"), params=params)

    async def governance_create_policy(self, name: str, **fields: Any) -> dict:
        return await self.post(self._build_url("/governance/policies"), data={"name": name, **fields})

    async def governance_create_version(self, policy_id: str, rules: list, **fields: Any) -> dict:
        return await self.post(self._build_url(f"/governance/policies/{policy_id}/versions"),
                               data={"rules": rules, **fields})

    async def governance_set_version_status(self, version_id: str, status: str, reason: str = "") -> dict:
        return await self.post(self._build_url(f"/governance/versions/{version_id}/status"),
                               data={"status": status, "reason": reason})

    async def governance_create_binding(self, policy_id: str, version_id: str, scope_type: str, **fields: Any) -> dict:
        return await self.post(self._build_url("/governance/bindings"),
                               data={"policy_id": policy_id, "version_id": version_id,
                                     "scope_type": scope_type, **fields})

    async def governance_evaluate(self, scope_type: str, **fields: Any) -> dict:
        return await self.post(self._build_url("/governance/evaluate"),
                               data={"scope_type": scope_type, **fields})

    async def governance_simulate(self, **fields: Any) -> dict:
        return await self.post(self._build_url("/governance/simulate"), data=fields)

    async def governance_list_decisions(self, limit: int = 100) -> dict:
        return await self.get(self._build_url("/governance/decisions"), params={"limit": limit})

    async def governance_create_exception(self, policy_id: str, justification: str, **fields: Any) -> dict:
        return await self.post(self._build_url("/governance/policy-exceptions"),
                               data={"policy_id": policy_id, "justification": justification, **fields})

    async def governance_approve_exception(self, exception_id: str, approver: str, **fields: Any) -> dict:
        return await self.post(self._build_url(f"/governance/policy-exceptions/{exception_id}/approve"),
                               data={"approver": approver, **fields})

    async def governance_posture(self, scope_type: str = "tenant") -> dict:
        return await self.get(self._build_url("/governance/posture"), params={"scope_type": scope_type})
