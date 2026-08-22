"""Identity provider service — OIDC, SAML, SSO configuration."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional


class IdentityProviderService:
    def __init__(self):
        self._providers: dict[str, dict] = {}
        self._external_identities: dict[str, dict] = {}

    def create(self, org_id: str, name: str, protocol: str, issuer: str = "", client_id: str = "", client_secret: str = "", metadata_url: str = "", certificate: str = "", attribute_mapping: Optional[dict] = None, group_mapping: Optional[dict] = None) -> dict:
        idp_id = str(uuid.uuid4())
        provider = {"id": idp_id, "organization_id": org_id, "name": name, "protocol": protocol, "issuer": issuer, "client_id": client_id, "client_secret_encrypted": "", "metadata_url": metadata_url, "certificate": certificate, "attribute_mapping": attribute_mapping or {}, "group_mapping": group_mapping or {}, "is_active": True, "config_validated": False, "last_sync_at": None, "sync_status": "idle", "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat()}
        self._providers[idp_id] = provider
        return provider

    def get(self, provider_id: str) -> Optional[dict]:
        return self._providers.get(provider_id)

    def list_for_org(self, org_id: str) -> list[dict]:
        return [p for p in self._providers.values() if p["organization_id"] == org_id]

    def update(self, provider_id: str, updates: dict) -> Optional[dict]:
        provider = self._providers.get(provider_id)
        if not provider:
            return None
        for key in ("name", "issuer", "client_id", "client_secret_encrypted", "metadata_url", "certificate", "attribute_mapping", "group_mapping", "is_active"):
            if key in updates:
                provider[key] = updates[key]
        provider["updated_at"] = datetime.now(timezone.utc).isoformat()
        return provider

    def delete(self, provider_id: str) -> bool:
        return self._providers.pop(provider_id, None) is not None

    def validate_config(self, provider_id: str) -> dict:
        provider = self._providers.get(provider_id)
        if not provider:
            return {"valid": False, "error": "Provider not found"}
        errors = []
        if not provider.get("issuer") and provider["protocol"] == "oidc":
            errors.append("issuer is required for OIDC")
        if not provider.get("certificate") and provider["protocol"] == "saml":
            errors.append("certificate is required for SAML")
        if not provider.get("client_id"):
            errors.append("client_id is required")
        is_valid = len(errors) == 0
        if is_valid:
            provider["config_validated"] = True
            provider["updated_at"] = datetime.now(timezone.utc).isoformat()
        return {"valid": is_valid, "errors": errors}

    def get_oidc_authorize_url(self, provider_id: str, redirect_uri: str, state: str, code_challenge: Optional[str] = None) -> Optional[str]:
        provider = self._providers.get(provider_id)
        if not provider or provider["protocol"] != "oidc":
            return None
        params = f"client_id={provider['client_id']}&redirect_uri={redirect_uri}&response_type=code&state={state}"
        if code_challenge:
            params += f"&code_challenge={code_challenge}&code_challenge_method=S256"
        return f"{provider['issuer']}/authorize?{params}"

    def validate_saml_assertion(self, provider_id: str, assertion_data: dict) -> dict:
        provider = self._providers.get(provider_id)
        if not provider:
            return {"valid": False, "error": "Provider not found"}
        return {"valid": True, "attributes": assertion_data.get("attributes", {}), "groups": assertion_data.get("groups", [])}

    def link_external_identity(self, provider_id: str, user_id: str, external_id: str, email: str, display_name: str = "", groups: Optional[list[str]] = None) -> dict:
        link_id = str(uuid.uuid4())
        link = {"id": link_id, "provider_id": provider_id, "user_id": user_id, "external_id": external_id, "email": email, "display_name": display_name, "groups": groups or [], "is_active": True, "linked_at": datetime.now(timezone.utc).isoformat()}
        self._external_identities[link_id] = link
        return link

    def list_external_identities(self, provider_id: Optional[str] = None, user_id: Optional[str] = None) -> list[dict]:
        links = list(self._external_identities.values())
        if provider_id:
            links = [l for l in links if l["provider_id"] == provider_id]
        if user_id:
            links = [l for l in links if l["user_id"] == user_id]
        return links

    def deactivate_external_identity(self, link_id: str) -> bool:
        link = self._external_identities.get(link_id)
        if not link:
            return False
        link["is_active"] = False
        link["deactivated_at"] = datetime.now(timezone.utc).isoformat()
        return True

    def get_stats(self, org_id: str) -> dict:
        providers = self.list_for_org(org_id)
        return {"total_providers": len(providers), "active": sum(1 for p in providers if p["is_active"]), "validated": sum(1 for p in providers if p.get("config_validated")), "protocols": list(set(p["protocol"] for p in providers))}


identity_provider_service = IdentityProviderService()
