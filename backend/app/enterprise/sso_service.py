"""SSO Service — Volume 40: OIDC, SAML, Session Management, MFA.

Provides enterprise SSO configuration, OIDC/SAML flows,
session management, and MFA enforcement.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from pydantic import BaseModel, Field


# ─── Models ────────────────────────────────────────────────────────────────

class SSOConnectionRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    organization_id: str
    protocol: str
    provider_name: str
    is_enforced: bool = False
    is_active: bool = True

    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret_ref: str = ""
    oidc_scopes: list[str] = Field(default_factory=lambda: ["openid", "email", "profile"])
    oidc_discovery_url: str = ""
    oidc_authorization_endpoint: str = ""
    oidc_token_endpoint: str = ""
    oidc_userinfo_endpoint: str = ""
    oidc_jwks_uri: str = ""
    oidc_end_session_endpoint: str = ""

    saml_entity_id: str = ""
    saml_sso_url: str = ""
    saml_slo_url: str = ""
    saml_certificate: str = ""
    saml_metadata_url: str = ""
    saml_signed_requests: bool = False
    saml_attribute_mapping: dict[str, str] = Field(default_factory=dict)
    saml_group_mapping: dict[str, str] = Field(default_factory=dict)

    allowed_redirect_uris: list[str] = Field(default_factory=list)
    default_role: str = "member"
    jit_provisioning: bool = True
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ExternalIdentityRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    organization_id: str
    sso_connection_id: str = ""
    provider: str
    provider_user_id: str
    provider_email: str = ""
    provider_username: str = ""
    provider_groups: list[str] = Field(default_factory=list)
    last_login_at: Optional[str] = None
    is_active: bool = True
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SessionRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    organization_id: str
    refresh_token_hash: str = ""
    ip_address: str = ""
    user_agent: str = ""
    device_info: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_at: str = ""
    last_activity_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    revoked_at: Optional[str] = None
    revoked_reason: str = ""


class ServiceAccountRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    organization_id: str
    name: str
    description: str = ""
    owner_id: str = ""
    client_id: str = Field(default_factory=lambda: f"sa_{secrets.token_urlsafe(24)}")
    client_secret_ref: str = ""
    scopes: list[str] = Field(default_factory=list)
    expires_at: Optional[str] = None
    last_rotated_at: Optional[str] = None
    is_active: bool = True
    last_used_at: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class GroupMappingRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    organization_id: str
    sso_connection_id: str = ""
    scim_directory_id: str = ""
    external_group_name: str
    mapped_role: str = ""
    mapped_workspace_ids: list[str] = Field(default_factory=list)
    mapped_project_ids: list[str] = Field(default_factory=list)
    mapped_policies: list[str] = Field(default_factory=list)
    is_active: bool = True
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ─── OIDC Discovery ───────────────────────────────────────────────────────

class OIDCDiscovery:
    """OIDC OpenID Connect Discovery client."""

    @staticmethod
    def build_discovery_url(issuer: str) -> str:
        return f"{issuer.rstrip('/')}/.well-known/openid-configuration"

    @staticmethod
    def parse_discovery(discovery_doc: dict[str, Any]) -> dict[str, Any]:
        return {
            "issuer": discovery_doc.get("issuer", ""),
            "authorization_endpoint": discovery_doc.get("authorization_endpoint", ""),
            "token_endpoint": discovery_doc.get("token_endpoint", ""),
            "userinfo_endpoint": discovery_doc.get("userinfo_endpoint", ""),
            "jwks_uri": discovery_doc.get("jwks_uri", ""),
            "end_session_endpoint": discovery_doc.get("end_session_endpoint", ""),
            "scopes_supported": discovery_doc.get("scopes_supported", []),
            "response_types_supported": discovery_doc.get("response_types_supported", []),
            "grant_types_supported": discovery_doc.get("grant_types_supported", []),
            "id_token_signing_alg_values_supported": discovery_doc.get("id_token_signing_alg_values_supported", []),
            "claims_supported": discovery_doc.get("claims_supported", []),
        }

    @staticmethod
    def build_authorization_url(
        authorization_endpoint: str,
        client_id: str,
        redirect_uri: str,
        state: str,
        scope: str = "openid email profile",
        nonce: str = "",
        code_challenge: str = "",
        code_challenge_method: str = "S256",
    ) -> str:
        import urllib.parse
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": scope,
            "state": state,
        }
        if nonce:
            params["nonce"] = nonce
        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = code_challenge_method
        return f"{authorization_endpoint}?{urllib.parse.urlencode(params)}"

    @staticmethod
    def extract_user_info(userinfo: dict[str, Any]) -> dict[str, Any]:
        return {
            "provider_user_id": userinfo.get("sub", ""),
            "email": userinfo.get("email", ""),
            "username": userinfo.get("preferred_username", userinfo.get("email", "")),
            "display_name": userinfo.get("name", ""),
            "groups": userinfo.get("groups", []),
            "roles": userinfo.get("roles", []),
        }


# ─── SAML Processing ──────────────────────────────────────────────────────

class SAMLProcessor:
    """SAML 2.0 assertion processing utilities."""

    @staticmethod
    def build_authn_request(
        entity_id: str,
        sso_url: str,
        acs_url: str,
        id: str = "",
        destination: str = "",
    ) -> dict[str, Any]:
        request_id = id or f"_id{uuid.uuid4().hex}"
        return {
            "id": request_id,
            "version": "2.0",
            "issue_instant": datetime.now(timezone.utc).isoformat(),
            "destination": destination or sso_url,
            "assertion_consumer_service_url": acs_url,
            "issuer": entity_id,
            "protocol_binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
        }

    @staticmethod
    def validate_replay(
        issue_instant: str,
        max_age_seconds: int = 300,
    ) -> bool:
        try:
            issued = datetime.fromisoformat(issue_instant)
            return (datetime.now(timezone.utc) - issued).total_seconds() <= max_age_seconds
        except (ValueError, TypeError):
            return False

    @staticmethod
    def extract_attributes(assertion_data: dict[str, Any]) -> dict[str, Any]:
        attributes = {}
        for attr_stmt in assertion_data.get("attribute_statements", []):
            for attr in attr_stmt.get("attributes", []):
                name = attr.get("name", "")
                values = attr.get("values", [])
                if values:
                    attributes[name] = values[0] if len(values) == 1 else values
        return attributes

    @staticmethod
    def map_attributes(
        attributes: dict[str, Any],
        mapping: dict[str, str],
    ) -> dict[str, Any]:
        result = {}
        for source_key, target_key in mapping.items():
            if source_key in attributes:
                result[target_key] = attributes[source_key]
        return result


# ─── SSO Service ──────────────────────────────────────────────────────────

class SSOService:
    """In-memory SSO service with OIDC, SAML, session, and MFA management."""

    _instance: Optional["SSOService"] = None

    def __new__(cls) -> "SSOService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._connections: dict[str, SSOConnectionRecord] = {}
        self._identities: dict[str, ExternalIdentityRecord] = {}
        self._sessions: dict[str, SessionRecord] = {}
        self._service_accounts: dict[str, ServiceAccountRecord] = {}
        self._group_mappings: dict[str, GroupMappingRecord] = {}
        self._oidc = OIDCDiscovery()
        self._saml = SAMLProcessor()
        self._initialized = True

    def reset(self) -> None:
        self._connections.clear()
        self._identities.clear()
        self._sessions.clear()
        self._service_accounts.clear()
        self._group_mappings.clear()

    # ── SSO Connections ─────────────────────────────────────────────────

    def create_sso_connection(
        self,
        organization_id: str,
        protocol: str,
        provider_name: str,
        is_enforced: bool = False,
        **oidc_kwargs: Any,
    ) -> SSOConnectionRecord:
        conn = SSOConnectionRecord(
            organization_id=organization_id,
            protocol=protocol,
            provider_name=provider_name,
            is_enforced=is_enforced,
            **oidc_kwargs,
        )
        self._connections[conn.id] = conn
        return conn

    def get_sso_connection(self, connection_id: str) -> Optional[SSOConnectionRecord]:
        return self._connections.get(connection_id)

    def get_sso_for_organization(self, organization_id: str) -> Optional[SSOConnectionRecord]:
        for conn in self._connections.values():
            if conn.organization_id == organization_id and conn.is_active:
                return conn
        return None

    def is_sso_enforced(self, organization_id: str) -> bool:
        conn = self.get_sso_for_organization(organization_id)
        return conn.is_enforced if conn else False

    def list_sso_connections(self, organization_id: str | None = None) -> list[SSOConnectionRecord]:
        results = list(self._connections.values())
        if organization_id:
            results = [c for c in results if c.organization_id == organization_id]
        return results

    def update_sso_connection(
        self,
        connection_id: str,
        is_enforced: bool | None = None,
        is_active: bool | None = None,
        **kwargs: Any,
    ) -> Optional[SSOConnectionRecord]:
        conn = self._connections.get(connection_id)
        if not conn:
            return None
        if is_enforced is not None:
            conn.is_enforced = is_enforced
        if is_active is not None:
            conn.is_active = is_active
        for k, v in kwargs.items():
            if hasattr(conn, k):
                setattr(conn, k, v)
        conn.updated_at = datetime.now(timezone.utc).isoformat()
        return conn

    def delete_sso_connection(self, connection_id: str) -> bool:
        if connection_id not in self._connections:
            return False
        del self._connections[connection_id]
        return True

    # ── OIDC Discovery ──────────────────────────────────────────────────

    def get_oidc_discovery(self, issuer: str) -> dict[str, Any]:
        return OIDCDiscovery.build_discovery_url(issuer)

    def build_oidc_authorization_url(
        self,
        connection_id: str,
        redirect_uri: str,
        state: str,
        code_challenge: str = "",
    ) -> str:
        conn = self._connections.get(connection_id)
        if not conn or conn.protocol != "oidc":
            return ""
        return OIDCDiscovery.build_authorization_url(
            authorization_endpoint=conn.oidc_authorization_endpoint,
            client_id=conn.oidc_client_id,
            redirect_uri=redirect_uri,
            state=state,
            scope=" ".join(conn.oidc_scopes),
            code_challenge=code_challenge,
        )

    def map_oidc_user(self, userinfo: dict[str, Any]) -> dict[str, Any]:
        return OIDCDiscovery.extract_user_info(userinfo)

    # ── SAML ────────────────────────────────────────────────────────────

    def build_saml_request(
        self,
        connection_id: str,
        acs_url: str,
    ) -> dict[str, Any]:
        conn = self._connections.get(connection_id)
        if not conn or conn.protocol != "saml":
            return {}
        return SAMLProcessor.build_authn_request(
            entity_id=conn.saml_entity_id,
            sso_url=conn.saml_sso_url,
            acs_url=acs_url,
        )

    def process_saml_assertion(
        self,
        connection_id: str,
        assertion_data: dict[str, Any],
    ) -> dict[str, Any]:
        conn = self._connections.get(connection_id)
        if not conn or conn.protocol != "saml":
            return {}
        attributes = SAMLProcessor.extract_attributes(assertion_data)
        mapped = SAMLProcessor.map_attributes(attributes, conn.saml_attribute_mapping)
        return {
            "provider_user_id": mapped.get("user_id", attributes.get("NameID", "")),
            "email": mapped.get("email", attributes.get("email", "")),
            "username": mapped.get("username", attributes.get("uid", "")),
            "groups": mapped.get("groups", []),
        }

    # ── External Identities ─────────────────────────────────────────────

    def link_identity(
        self,
        user_id: str,
        organization_id: str,
        provider: str,
        provider_user_id: str,
        provider_email: str = "",
        provider_username: str = "",
        provider_groups: list[str] | None = None,
        sso_connection_id: str = "",
    ) -> ExternalIdentityRecord:
        identity = ExternalIdentityRecord(
            user_id=user_id,
            organization_id=organization_id,
            provider=provider,
            provider_user_id=provider_user_id,
            provider_email=provider_email,
            provider_username=provider_username,
            provider_groups=provider_groups or [],
            sso_connection_id=ssoid if (ssoid := sso_connection_id) else "",
        )
        self._identities[identity.id] = identity
        return identity

    def get_identity(self, identity_id: str) -> Optional[ExternalIdentityRecord]:
        return self._identities.get(identity_id)

    def find_identity_by_provider(
        self,
        provider: str,
        provider_user_id: str,
    ) -> Optional[ExternalIdentityRecord]:
        for identity in self._identities.values():
            if identity.provider == provider and identity.provider_user_id == provider_user_id:
                return identity
        return None

    def list_identities(
        self,
        user_id: str | None = None,
        organization_id: str | None = None,
    ) -> list[ExternalIdentityRecord]:
        results = list(self._identities.values())
        if user_id:
            results = [i for i in results if i.user_id == user_id]
        if organization_id:
            results = [i for i in results if i.organization_id == organization_id]
        return results

    def deactivate_identity(self, identity_id: str) -> Optional[ExternalIdentityRecord]:
        identity = self._identities.get(identity_id)
        if not identity:
            return None
        identity.is_active = False
        return identity

    # ── Session Management ──────────────────────────────────────────────

    def create_session(
        self,
        user_id: str,
        organization_id: str,
        ip_address: str = "",
        user_agent: str = "",
        expires_in_hours: int = 720,
    ) -> SessionRecord:
        session = SessionRecord(
            user_id=user_id,
            organization_id=organization_id,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=(datetime.now(timezone.utc) + timedelta(hours=expires_in_hours)).isoformat(),
        )
        self._sessions[session.id] = session
        return session

    def get_session(self, session_id: str) -> Optional[SessionRecord]:
        return self._sessions.get(session_id)

    def list_sessions(
        self,
        user_id: str | None = None,
        organization_id: str | None = None,
        active_only: bool = True,
    ) -> list[SessionRecord]:
        results = list(self._sessions.values())
        if user_id:
            results = [s for s in results if s.user_id == user_id]
        if organization_id:
            results = [s for s in results if s.organization_id == organization_id]
        if active_only:
            results = [s for s in results if not s.revoked_at]
        return results

    def revoke_session(self, session_id: str, reason: str = "manual") -> Optional[SessionRecord]:
        session = self._sessions.get(session_id)
        if not session:
            return None
        session.revoked_at = datetime.now(timezone.utc).isoformat()
        session.revoked_reason = reason
        return session

    def revoke_all_user_sessions(
        self,
        user_id: str,
        except_session_id: str = "",
        reason: str = "bulk_revoke",
    ) -> int:
        count = 0
        for session in self._sessions.values():
            if session.user_id == user_id and not session.revoked_at:
                if session.id != except_session_id:
                    session.revoked_at = datetime.now(timezone.utc).isoformat()
                    session.revoked_reason = reason
                    count += 1
        return count

    def detect_suspicious_sessions(self, user_id: str) -> list[SessionRecord]:
        sessions = self.list_sessions(user_id=user_id)
        if len(sessions) <= 1:
            return []
        suspicious = []
        user_agents = {}
        for s in sessions:
            ua = s.user_agent or "unknown"
            if ua not in user_agents:
                user_agents[ua] = []
            user_agents[ua].append(s)
        for ua, group in user_agents.items():
            if len(group) > 3:
                suspicious.extend(group)
        return suspicious

    def cleanup_expired_sessions(self) -> int:
        now = datetime.now(timezone.utc).isoformat()
        count = 0
        for session in self._sessions.values():
            if not session.revoked_at and session.expires_at and session.expires_at < now:
                session.revoked_at = now
                session.revoked_reason = "expired"
                count += 1
        return count

    # ── Service Accounts ────────────────────────────────────────────────

    def create_service_account(
        self,
        organization_id: str,
        name: str,
        description: str = "",
        owner_id: str = "",
        scopes: list[str] | None = None,
        expires_at: str | None = None,
    ) -> ServiceAccountRecord:
        secret = secrets.token_urlsafe(48)
        sa = ServiceAccountRecord(
            organization_id=organization_id,
            name=name,
            description=description,
            owner_id=owner_id,
            client_secret_ref=hashlib.sha256(secret.encode()).hexdigest(),
            scopes=scopes or [],
            expires_at=expires_at,
        )
        self._service_accounts[sa.id] = sa
        return sa

    def get_service_account(self, sa_id: str) -> Optional[ServiceAccountRecord]:
        return self._service_accounts.get(sa_id)

    def list_service_accounts(self, organization_id: str) -> list[ServiceAccountRecord]:
        return [sa for sa in self._service_accounts.values() if sa.organization_id == organization_id]

    def rotate_service_account(self, sa_id: str) -> Optional[dict[str, str]]:
        sa = self._service_accounts.get(sa_id)
        if not sa or not sa.is_active:
            return None
        new_secret = secrets.token_urlsafe(48)
        sa.client_secret_ref = hashlib.sha256(new_secret.encode()).hexdigest()
        sa.last_rotated_at = datetime.now(timezone.utc).isoformat()
        return {"client_id": sa.client_id, "client_secret": new_secret}

    def revoke_service_account(self, sa_id: str) -> Optional[ServiceAccountRecord]:
        sa = self._service_accounts.get(sa_id)
        if not sa:
            return None
        sa.is_active = False
        return sa

    # ── Group Mapping ───────────────────────────────────────────────────

    def create_group_mapping(
        self,
        organization_id: str,
        external_group_name: str,
        mapped_role: str = "",
        mapped_workspace_ids: list[str] | None = None,
        mapped_project_ids: list[str] | None = None,
        mapped_policies: list[str] | None = None,
        sso_connection_id: str = "",
        scim_directory_id: str = "",
    ) -> GroupMappingRecord:
        mapping = GroupMappingRecord(
            organization_id=organization_id,
            external_group_name=external_group_name,
            mapped_role=mapped_role,
            mapped_workspace_ids=mapped_workspace_ids or [],
            mapped_project_ids=mapped_project_ids or [],
            mapped_policies=mapped_policies or [],
            sso_connection_id=sso_connection_id,
            scim_directory_id=scim_directory_id,
        )
        self._group_mappings[mapping.id] = mapping
        return mapping

    def get_group_mapping(self, mapping_id: str) -> Optional[GroupMappingRecord]:
        return self._group_mappings.get(mapping_id)

    def list_group_mappings(
        self,
        organization_id: str,
        external_group_name: str | None = None,
    ) -> list[GroupMappingRecord]:
        results = [m for m in self._group_mappings.values() if m.organization_id == organization_id]
        if external_group_name:
            results = [m for m in results if m.external_group_name == external_group_name]
        return results

    def resolve_group_roles(self, organization_id: str, groups: list[str]) -> dict[str, Any]:
        mapped_role = ""
        workspace_ids: list[str] = []
        project_ids: list[str] = []
        policies: list[str] = []
        for mapping in self.list_group_mappings(organization_id):
            if mapping.external_group_name in groups:
                if mapping.mapped_role and not mapped_role:
                    mapped_role = mapping.mapped_role
                workspace_ids.extend(mapping.mapped_workspace_ids)
                project_ids.extend(mapping.mapped_project_ids)
                policies.extend(mapping.mapped_policies)
        return {
            "role": mapped_role or "member",
            "workspace_ids": list(set(workspace_ids)),
            "project_ids": list(set(project_ids)),
            "policies": list(set(policies)),
        }

    def delete_group_mapping(self, mapping_id: str) -> bool:
        if mapping_id not in self._group_mappings:
            return False
        del self._group_mappings[mapping_id]
        return True

    # ── Metrics ─────────────────────────────────────────────────────────

    def get_metrics(self, organization_id: str | None = None) -> dict[str, Any]:
        connections = self.list_sso_connections(organization_id)
        sessions = self.list_sessions(organization_id=organization_id, active_only=False)
        sa = self.list_service_accounts(organization_id) if organization_id else []
        return {
            "sso_connections": len(connections),
            "active_sessions": sum(1 for s in sessions if not s.revoked_at),
            "total_sessions": len(sessions),
            "service_accounts": len(sa),
            "active_service_accounts": sum(1 for s in sa if s.is_active),
            "group_mappings": len(self.list_group_mappings(organization_id)) if organization_id else 0,
        }
