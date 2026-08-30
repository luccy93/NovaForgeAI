"""Zero Trust SDK mixin — Volume 64."""

from typing import Any, Dict, Optional


class ZeroTrustMixin:
    """Synchronous Zero Trust mixin."""

    def zt_authorize(self, identity: str, resource: str, action: str, **kwargs: Any) -> dict:
        payload: Dict[str, Any] = {"identity": identity, "resource": resource, "action": action}
        for k in ("session_id_hash", "device_context", "region", "data_classification", "risk_state"):
            if k in kwargs and kwargs[k] is not None:
                payload[k] = kwargs[k]
        return self.post(self._build_url("/zero-trust/authorize"), data=payload)

    def zt_create_session(self, identity_id: str, **kwargs: Any) -> dict:
        payload: Dict[str, Any] = {"identity_id": identity_id}
        for k in ("scope", "device_context", "region", "ip", "user_agent", "auth_method", "absolute_timeout", "idle_timeout"):
            if k in kwargs and kwargs[k] is not None:
                payload[k] = kwargs[k]
        return self.post(self._build_url("/zero-trust/sessions"), data=payload)

    def zt_list_sessions(self, identity_id: str) -> dict:
        return self.get(self._build_url("/zero-trust/sessions"), params={"identity_id": identity_id})

    def zt_revoke_session(self, session_id_hash: str) -> dict:
        return self.post(self._build_url(f"/zero-trust/sessions/{session_id_hash}/revoke"), data={})

    def zt_revoke_all_sessions(self, identity_id: str) -> dict:
        return self.post(self._build_url("/zero-trust/sessions/revoke-all"), params={"identity_id": identity_id})

    def zt_create_credential(self, owner_id: str, credential_type: str, raw_value: str, **kwargs: Any) -> dict:
        payload: Dict[str, Any] = {"owner_id": owner_id, "credential_type": credential_type, "raw_value": raw_value}
        for k in ("scope", "expires_in_days", "owner_type"):
            if k in kwargs and kwargs[k] is not None:
                payload[k] = kwargs[k]
        return self.post(self._build_url("/zero-trust/credentials"), data=payload)

    def zt_list_credentials(self, owner_id: str | None = None, limit: int = 20) -> dict:
        params: Dict[str, Any] = {"limit": limit}
        if owner_id:
            params["owner_id"] = owner_id
        return self.get(self._build_url("/zero-trust/credentials"), params=params)

    def zt_revoke_credential(self, credential_id: str) -> dict:
        return self.post(self._build_url(f"/zero-trust/credentials/{credential_id}/revoke"), data={})

    def zt_rotate_credential(self, credential_id: str, raw_value: str) -> dict:
        return self.post(self._build_url(f"/zero-trust/credentials/{credential_id}/rotate"), data={"raw_value": raw_value})

    def zt_request_access(self, identity_id: str, resource: str, action: str, reason: str, **kwargs: Any) -> dict:
        payload: Dict[str, Any] = {"identity_id": identity_id, "resource": resource, "action": action, "reason": reason}
        for k in ("duration_seconds", "scope", "privilege_level"):
            if k in kwargs and kwargs[k] is not None:
                payload[k] = kwargs[k]
        return self.post(self._build_url("/zero-trust/access-requests"), data=payload)

    def zt_list_access_requests(self, status: str | None = None, limit: int = 20) -> dict:
        params: Dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        return self.get(self._build_url("/zero-trust/access-requests"), params=params)

    def zt_approve_access(self, access_id: str, binding_hash: str | None = None) -> dict:
        payload: Dict[str, Any] = {}
        if binding_hash:
            payload["binding_hash"] = binding_hash
        return self.post(self._build_url(f"/zero-trust/access-requests/{access_id}/approve"), data=payload)

    def zt_revoke_access(self, access_id: str) -> dict:
        return self.post(self._build_url(f"/zero-trust/access-requests/{access_id}/revoke"), data={})

    def zt_create_review(self, review_type: str = "periodic", scope: str = "all") -> dict:
        return self.post(self._build_url("/zero-trust/reviews"), data={"review_type": review_type, "scope": scope})

    def zt_list_reviews(self, limit: int = 20) -> dict:
        return self.get(self._build_url("/zero-trust/reviews"), params={"limit": limit})

    def zt_certify_review(self, review_id: str, results: dict | None = None) -> dict:
        return self.post(self._build_url(f"/zero-trust/reviews/{review_id}/certify"), data={"certify": True, "results": results or {}})

    def zt_list_privileged(self, limit: int = 20) -> dict:
        return self.get(self._build_url("/zero-trust/privileged-access"), params={"limit": limit})

    def zt_evaluate_risk(self, identity: str, signals: dict | None = None, identity_type: str = "human") -> dict:
        payload: Dict[str, Any] = {"identity": identity, "identity_type": identity_type}
        if signals is not None:
            payload["signals"] = signals
        return self.post(self._build_url("/zero-trust/identity-risk/evaluate"), data=payload)

    def zt_get_risk(self, identity_id: str) -> dict:
        return self.get(self._build_url(f"/zero-trust/identity-risk/{identity_id}"))

    # Commit 2 additions
    def zt_reevaluate(self, session_id_hash: str, signals: dict | None = None) -> dict:
        return self.post(self._build_url("/zero-trust/continuous/reevaluate"), data={"session_id_hash": session_id_hash, "signals": signals or {}})

    def zt_continuous_check(self, session_id_hash: str, resource: str, action: str) -> dict:
        return self.post(self._build_url("/zero-trust/continuous/check"), data={"session_id_hash": session_id_hash, "resource": resource, "action": action})

    def zt_get_posture(self) -> dict:
        return self.get(self._build_url("/zero-trust/posture"))

    def zt_get_identity_posture(self) -> dict:
        return self.get(self._build_url("/zero-trust/identity-posture"))

    def zt_get_access_graph(self, identity: str, depth: int = 2) -> dict:
        return self.get(self._build_url("/zero-trust/access-graph"), params={"identity": identity, "depth": depth})

    def zt_simulate(self, identity: str, action: str, resource: str, context: dict | None = None) -> dict:
        return self.post(self._build_url("/zero-trust/policy-simulation"), data={"identity": identity, "action": action, "resource": resource, "context": context or {}})

    def zt_what_if(self, permission: str, remove: bool = True) -> dict:
        return self.post(self._build_url("/zero-trust/policy-simulation/what-if"), data={"permission": permission, "remove": remove})

    def zt_get_blast_radius(self, identity_id: str) -> dict:
        return self.get(self._build_url(f"/zero-trust/blast-radius/{identity_id}"))

    def zt_get_access_anomalies(self, since_hours: int = 24) -> dict:
        return self.get(self._build_url("/zero-trust/access-anomalies"), params={"since_hours": since_hours})

    def zt_list_campaigns(self, limit: int = 20) -> dict:
        return self.get(self._build_url("/zero-trust/review-campaigns"), params={"limit": limit})

    def zt_create_campaign(self, scope: str = "all", reviewers: list | None = None) -> dict:
        return self.post(self._build_url("/zero-trust/review-campaigns"), data={"scope": scope, "reviewers": reviewers or []})


class AsyncZeroTrustMixin:
    """Async Zero Trust mixin."""

    async def zt_authorize(self, identity: str, resource: str, action: str, **kwargs: Any) -> dict:
        payload: Dict[str, Any] = {"identity": identity, "resource": resource, "action": action}
        for k in ("session_id_hash", "device_context", "region", "data_classification", "risk_state"):
            if k in kwargs and kwargs[k] is not None:
                payload[k] = kwargs[k]
        return await self.post(self._build_url("/zero-trust/authorize"), data=payload)

    async def zt_create_session(self, identity_id: str, **kwargs: Any) -> dict:
        payload: Dict[str, Any] = {"identity_id": identity_id}
        for k in ("scope", "device_context", "region", "ip", "user_agent", "auth_method", "absolute_timeout", "idle_timeout"):
            if k in kwargs and kwargs[k] is not None:
                payload[k] = kwargs[k]
        return await self.post(self._build_url("/zero-trust/sessions"), data=payload)

    async def zt_list_sessions(self, identity_id: str) -> dict:
        return await self.get(self._build_url("/zero-trust/sessions"), params={"identity_id": identity_id})

    async def zt_revoke_session(self, session_id_hash: str) -> dict:
        return await self.post(self._build_url(f"/zero-trust/sessions/{session_id_hash}/revoke"), data={})

    async def zt_revoke_all_sessions(self, identity_id: str) -> dict:
        return await self.post(self._build_url("/zero-trust/sessions/revoke-all"), params={"identity_id": identity_id})

    async def zt_create_credential(self, owner_id: str, credential_type: str, raw_value: str, **kwargs: Any) -> dict:
        payload: Dict[str, Any] = {"owner_id": owner_id, "credential_type": credential_type, "raw_value": raw_value}
        for k in ("scope", "expires_in_days", "owner_type"):
            if k in kwargs and kwargs[k] is not None:
                payload[k] = kwargs[k]
        return await self.post(self._build_url("/zero-trust/credentials"), data=payload)

    async def zt_list_credentials(self, owner_id: str | None = None, limit: int = 20) -> dict:
        params: Dict[str, Any] = {"limit": limit}
        if owner_id:
            params["owner_id"] = owner_id
        return await self.get(self._build_url("/zero-trust/credentials"), params=params)

    async def zt_revoke_credential(self, credential_id: str) -> dict:
        return await self.post(self._build_url(f"/zero-trust/credentials/{credential_id}/revoke"), data={})

    async def zt_rotate_credential(self, credential_id: str, raw_value: str) -> dict:
        return await self.post(self._build_url(f"/zero-trust/credentials/{credential_id}/rotate"), data={"raw_value": raw_value})

    async def zt_request_access(self, identity_id: str, resource: str, action: str, reason: str, **kwargs: Any) -> dict:
        payload: Dict[str, Any] = {"identity_id": identity_id, "resource": resource, "action": action, "reason": reason}
        for k in ("duration_seconds", "scope", "privilege_level"):
            if k in kwargs and kwargs[k] is not None:
                payload[k] = kwargs[k]
        return await self.post(self._build_url("/zero-trust/access-requests"), data=payload)

    async def zt_list_access_requests(self, status: str | None = None, limit: int = 20) -> dict:
        params: Dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        return await self.get(self._build_url("/zero-trust/access-requests"), params=params)

    async def zt_approve_access(self, access_id: str, binding_hash: str | None = None) -> dict:
        payload: Dict[str, Any] = {}
        if binding_hash:
            payload["binding_hash"] = binding_hash
        return await self.post(self._build_url(f"/zero-trust/access-requests/{access_id}/approve"), data=payload)

    async def zt_revoke_access(self, access_id: str) -> dict:
        return await self.post(self._build_url(f"/zero-trust/access-requests/{access_id}/revoke"), data={})

    async def zt_create_review(self, review_type: str = "periodic", scope: str = "all") -> dict:
        return await self.post(self._build_url("/zero-trust/reviews"), data={"review_type": review_type, "scope": scope})

    async def zt_list_reviews(self, limit: int = 20) -> dict:
        return await self.get(self._build_url("/zero-trust/reviews"), params={"limit": limit})

    async def zt_certify_review(self, review_id: str, results: dict | None = None) -> dict:
        return await self.post(self._build_url(f"/zero-trust/reviews/{review_id}/certify"), data={"certify": True, "results": results or {}})

    async def zt_list_privileged(self, limit: int = 20) -> dict:
        return await self.get(self._build_url("/zero-trust/privileged-access"), params={"limit": limit})

    async def zt_evaluate_risk(self, identity: str, signals: dict | None = None, identity_type: str = "human") -> dict:
        payload: Dict[str, Any] = {"identity": identity, "identity_type": identity_type}
        if signals is not None:
            payload["signals"] = signals
        return await self.post(self._build_url("/zero-trust/identity-risk/evaluate"), data=payload)

    async def zt_get_risk(self, identity_id: str) -> dict:
        return await self.get(self._build_url(f"/zero-trust/identity-risk/{identity_id}"))

    async def zt_reevaluate(self, session_id_hash: str, signals: dict | None = None) -> dict:
        return await self.post(self._build_url("/zero-trust/continuous/reevaluate"), data={"session_id_hash": session_id_hash, "signals": signals or {}})

    async def zt_continuous_check(self, session_id_hash: str, resource: str, action: str) -> dict:
        return await self.post(self._build_url("/zero-trust/continuous/check"), data={"session_id_hash": session_id_hash, "resource": resource, "action": action})

    async def zt_get_posture(self) -> dict:
        return await self.get(self._build_url("/zero-trust/posture"))

    async def zt_get_identity_posture(self) -> dict:
        return await self.get(self._build_url("/zero-trust/identity-posture"))

    async def zt_get_access_graph(self, identity: str, depth: int = 2) -> dict:
        return await self.get(self._build_url("/zero-trust/access-graph"), params={"identity": identity, "depth": depth})

    async def zt_simulate(self, identity: str, action: str, resource: str, context: dict | None = None) -> dict:
        return await self.post(self._build_url("/zero-trust/policy-simulation"), data={"identity": identity, "action": action, "resource": resource, "context": context or {}})

    async def zt_what_if(self, permission: str, remove: bool = True) -> dict:
        return await self.post(self._build_url("/zero-trust/policy-simulation/what-if"), data={"permission": permission, "remove": remove})

    async def zt_get_blast_radius(self, identity_id: str) -> dict:
        return await self.get(self._build_url(f"/zero-trust/blast-radius/{identity_id}"))

    async def zt_get_access_anomalies(self, since_hours: int = 24) -> dict:
        return await self.get(self._build_url("/zero-trust/access-anomalies"), params={"since_hours": since_hours})

    async def zt_list_campaigns(self, limit: int = 20) -> dict:
        return await self.get(self._build_url("/zero-trust/review-campaigns"), params={"limit": limit})

    async def zt_create_campaign(self, scope: str = "all", reviewers: list | None = None) -> dict:
        return await self.post(self._build_url("/zero-trust/review-campaigns"), data={"scope": scope, "reviewers": reviewers or []})
