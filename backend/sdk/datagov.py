"""Data Governance SDK mixin — Volume 57.

Mirrors :mod:`backend.sdk.release` and expects the host class to provide
``self.get/post/put/delete`` and ``self._build_url``.
"""

from typing import Any, Optional


class GovernanceMixin:
    def governance_register_asset(self, data: dict) -> dict:
        return self.post(self._build_url("/governance/assets"), data=data)

    def governance_get_asset(self, asset_id: str) -> dict:
        return self.get(self._build_url(f"/governance/assets/{asset_id}"))

    def governance_list_assets(self, **params: Any) -> list:
        return self.get(self._build_url("/governance/assets"), params=params)

    def governance_discover_assets(self) -> dict:
        return self.post(self._build_url("/governance/assets/discover"), data={})

    def governance_classify(self, asset_id: str, level: str, source: str = "user", **kwargs: Any) -> dict:
        payload = {"level": level, "source": source, **kwargs}
        return self.post(self._build_url(f"/governance/assets/{asset_id}/classify"), data=payload)

    def governance_auto_classify(self, asset_id: str, content_sample: str) -> dict:
        return self.post(self._build_url("/governance/classify/auto"), data={"asset_id": asset_id, "content_sample": content_sample})

    def governance_detect_sensitive(self, text: str) -> dict:
        return self.post(self._build_url("/governance/classify/detect"), data={"text": text})

    def governance_list_classifications(self, asset_id: str) -> list:
        return self.get(self._build_url(f"/governance/assets/{asset_id}/classifications"))

    def governance_record_lineage(self, source_asset: str, target_asset: str, transformation: str, evidence: str, stage: str = "transform") -> dict:
        return self.post(self._build_url("/governance/lineage"), data={
            "source_asset": source_asset, "target_asset": target_asset,
            "transformation": transformation, "evidence": evidence, "stage": stage,
        })

    def governance_lineage_upstream(self, asset_id: str, depth: int = 10) -> dict:
        return self.get(self._build_url(f"/governance/lineage/{asset_id}/upstream"), params={"depth": depth})

    def governance_lineage_downstream(self, asset_id: str, depth: int = 10) -> dict:
        return self.get(self._build_url(f"/governance/lineage/{asset_id}/downstream"), params={"depth": depth})

    def governance_lineage_impact(self, asset_id: str) -> dict:
        return self.get(self._build_url(f"/governance/lineage/{asset_id}/impact"))

    def governance_create_retention_policy(self, data: dict) -> dict:
        return self.post(self._build_url("/governance/retention/policies"), data=data)

    def governance_list_retention_policies(self) -> list:
        return self.get(self._build_url("/governance/retention/policies"))

    def governance_check_expired(self) -> dict:
        return self.get(self._build_url("/governance/retention/check"))

    def governance_create_legal_hold(self, scope: str, reason: str) -> dict:
        return self.post(self._build_url("/governance/legal-holds"), data={"scope": scope, "reason": reason})

    def governance_release_legal_hold(self, hold_id: str) -> dict:
        return self.delete(self._build_url(f"/governance/legal-holds/{hold_id}"))

    def governance_list_legal_holds(self) -> list:
        return self.get(self._build_url("/governance/legal-holds"))

    def governance_create_request(self, request_type: str, subject: str, scope: Optional[dict] = None) -> dict:
        return self.post(self._build_url("/governance/requests"), data={
            "request_type": request_type, "subject": subject, "scope": scope or {},
        })

    def governance_list_requests(self, **params: Any) -> list:
        return self.get(self._build_url("/governance/requests"), params=params)

    def governance_verify_request(self, request_id: str, method: str) -> dict:
        return self.post(self._build_url(f"/governance/requests/{request_id}/verify"), data={"method": method})

    def governance_approve_request(self, request_id: str, decision: str) -> dict:
        return self.post(self._build_url(f"/governance/requests/{request_id}/approve"), data={"decision": decision})

    def governance_complete_request(self, request_id: str, systems: Optional[list] = None, completion: Optional[dict] = None) -> dict:
        return self.post(self._build_url(f"/governance/requests/{request_id}/complete"), data={
            "systems": systems or [], "completion": completion or {},
        })

    def governance_create_export(self, scope: dict, data_sources: list, format: str = "json", ttl_hours: int = 24) -> dict:
        return self.post(self._build_url("/governance/exports"), data={
            "scope": scope, "data_sources": data_sources, "format": format, "ttl_hours": ttl_hours,
        })

    def governance_get_export(self, export_id: str) -> dict:
        return self.get(self._build_url(f"/governance/exports/{export_id}"))

    def governance_verify_export_token(self, export_id: str, token: str) -> dict:
        return self.post(self._build_url(f"/governance/exports/{export_id}/verify"), data={"token": token})

    def governance_revoke_export(self, export_id: str) -> dict:
        return self.post(self._build_url(f"/governance/exports/{export_id}/revoke"), data={})

    def governance_register_processor(self, provider: str, purpose: str, data_categories: list, region: Optional[str] = None) -> dict:
        return self.post(self._build_url("/governance/processors"), data={
            "provider": provider, "purpose": purpose, "data_categories": data_categories, "region": region,
        })

    def governance_list_processors(self) -> list:
        return self.get(self._build_url("/governance/processors"))

    def governance_revoke_processor(self, processor_id: str, reason: str = "") -> dict:
        return self.post(self._build_url(f"/governance/processors/{processor_id}/revoke"), data={"reason": reason})

    def governance_record_consent(self, subject: str, purpose: str, version: str = "1.0") -> dict:
        return self.post(self._build_url("/governance/consents"), data={
            "subject": subject, "purpose": purpose, "version": version,
        })

    def governance_withdraw_consent(self, consent_id: str) -> dict:
        return self.post(self._build_url(f"/governance/consents/{consent_id}/withdraw"), data={})

    def governance_evaluate_policy(self, resource: str, policy_type: str, context: Optional[dict] = None) -> dict:
        return self.post(self._build_url("/governance/policies/evaluate"), data={
            "resource": resource, "policy_type": policy_type, "context": context or {},
        })

    def governance_simulate_policy(self, resource: str, context: Optional[dict] = None) -> dict:
        return self.post(self._build_url("/governance/policies/simulate"), data={
            "resource": resource, "context": context or {},
        })

    def governance_policy_decisions(self, **params: Any) -> list:
        return self.get(self._build_url("/governance/policies/decisions"), params=params)

    def governance_create_control(self, framework: str, control_id: str, owner: Optional[str] = None) -> dict:
        return self.post(self._build_url("/governance/controls"), data={
            "framework": framework, "control_id": control_id, "owner": owner,
        })

    def governance_list_controls(self, **params: Any) -> list:
        return self.get(self._build_url("/governance/controls"), params=params)

    def governance_collect_evidence(self, control_id: str, evidence_type: str, source: str, valid_until: Optional[str] = None) -> dict:
        return self.post(self._build_url(f"/governance/controls/{control_id}/evidence"), data={
            "evidence_type": evidence_type, "source": source, "valid_until": valid_until,
        })

    def governance_assess_control(self, control_id: str, status: str) -> dict:
        return self.post(self._build_url(f"/governance/controls/{control_id}/assess"), data={"status": status})

    def governance_audit_package(self, framework: str) -> dict:
        return self.get(self._build_url("/governance/controls/package"), params={"framework": framework})

    def governance_create_exception(self, reason: str, expires_at: str, policy_id: Optional[str] = None, resource: Optional[str] = None) -> dict:
        return self.post(self._build_url("/governance/exceptions"), data={
            "reason": reason, "expires_at": expires_at, "policy_id": policy_id, "resource": resource,
        })

    def governance_list_exceptions(self) -> list:
        return self.get(self._build_url("/governance/exceptions"))

    def governance_dlp_scan(self, destination: str, content_sample: str, classification: str = "INTERNAL") -> dict:
        return self.post(self._build_url("/governance/dlp/scan"), data={
            "destination": destination, "content_sample": content_sample, "classification": classification,
        })

    def governance_dlp_events(self, **params: Any) -> list:
        return self.get(self._build_url("/governance/dlp/events"), params=params)

    def governance_dlp_redact(self, text: str, classification: str = "RESTRICTED") -> dict:
        return self.post(self._build_url("/governance/dlp/redact"), data={"text": text, "classification": classification})

    def governance_risk(self, asset_id: str) -> dict:
        return self.get(self._build_url(f"/governance/risk/{asset_id}"))

    def governance_dashboard(self) -> dict:
        return self.get(self._build_url("/governance/dashboard"))


class AsyncGovernanceMixin:
    async def governance_register_asset(self, data: dict) -> dict:
        return await self.post(self._build_url("/governance/assets"), data=data)

    async def governance_get_asset(self, asset_id: str) -> dict:
        return await self.get(self._build_url(f"/governance/assets/{asset_id}"))

    async def governance_list_assets(self, **params: Any) -> list:
        return await self.get(self._build_url("/governance/assets"), params=params)

    async def governance_discover_assets(self) -> dict:
        return await self.post(self._build_url("/governance/assets/discover"), data={})

    async def governance_classify(self, asset_id: str, level: str, source: str = "user", **kwargs: Any) -> dict:
        payload = {"level": level, "source": source, **kwargs}
        return await self.post(self._build_url(f"/governance/assets/{asset_id}/classify"), data=payload)

    async def governance_detect_sensitive(self, text: str) -> dict:
        return await self.post(self._build_url("/governance/classify/detect"), data={"text": text})

    async def governance_record_lineage(self, source_asset: str, target_asset: str, transformation: str, evidence: str, stage: str = "transform") -> dict:
        return await self.post(self._build_url("/governance/lineage"), data={
            "source_asset": source_asset, "target_asset": target_asset,
            "transformation": transformation, "evidence": evidence, "stage": stage,
        })

    async def governance_lineage_upstream(self, asset_id: str, depth: int = 10) -> dict:
        return await self.get(self._build_url(f"/governance/lineage/{asset_id}/upstream"), params={"depth": depth})

    async def governance_lineage_impact(self, asset_id: str) -> dict:
        return await self.get(self._build_url(f"/governance/lineage/{asset_id}/impact"))

    async def governance_create_retention_policy(self, data: dict) -> dict:
        return await self.post(self._build_url("/governance/retention/policies"), data=data)

    async def governance_check_expired(self) -> dict:
        return await self.get(self._build_url("/governance/retention/check"))

    async def governance_create_legal_hold(self, scope: str, reason: str) -> dict:
        return await self.post(self._build_url("/governance/legal-holds"), data={"scope": scope, "reason": reason})

    async def governance_create_request(self, request_type: str, subject: str, scope: Optional[dict] = None) -> dict:
        return await self.post(self._build_url("/governance/requests"), data={
            "request_type": request_type, "subject": subject, "scope": scope or {},
        })

    async def governance_verify_request(self, request_id: str, method: str) -> dict:
        return await self.post(self._build_url(f"/governance/requests/{request_id}/verify"), data={"method": method})

    async def governance_complete_request(self, request_id: str, systems: Optional[list] = None) -> dict:
        return await self.post(self._build_url(f"/governance/requests/{request_id}/complete"), data={"systems": systems or []})

    async def governance_create_export(self, scope: dict, data_sources: list, format: str = "json", ttl_hours: int = 24) -> dict:
        return await self.post(self._build_url("/governance/exports"), data={
            "scope": scope, "data_sources": data_sources, "format": format, "ttl_hours": ttl_hours,
        })

    async def governance_revoke_export(self, export_id: str) -> dict:
        return await self.post(self._build_url(f"/governance/exports/{export_id}/revoke"), data={})

    async def governance_evaluate_policy(self, resource: str, policy_type: str, context: Optional[dict] = None) -> dict:
        return await self.post(self._build_url("/governance/policies/evaluate"), data={
            "resource": resource, "policy_type": policy_type, "context": context or {},
        })

    async def governance_simulate_policy(self, resource: str, context: Optional[dict] = None) -> dict:
        return await self.post(self._build_url("/governance/policies/simulate"), data={
            "resource": resource, "context": context or {},
        })

    async def governance_collect_evidence(self, control_id: str, evidence_type: str, source: str, valid_until: Optional[str] = None) -> dict:
        return await self.post(self._build_url(f"/governance/controls/{control_id}/evidence"), data={
            "evidence_type": evidence_type, "source": source, "valid_until": valid_until,
        })

    async def governance_assess_control(self, control_id: str, status: str) -> dict:
        return await self.post(self._build_url(f"/governance/controls/{control_id}/assess"), data={"status": status})

    async def governance_dlp_scan(self, destination: str, content_sample: str, classification: str = "INTERNAL") -> dict:
        return await self.post(self._build_url("/governance/dlp/scan"), data={
            "destination": destination, "content_sample": content_sample, "classification": classification,
        })

    async def governance_risk(self, asset_id: str) -> dict:
        return await self.get(self._build_url(f"/governance/risk/{asset_id}"))
