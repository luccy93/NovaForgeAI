"""Integration Registry Service — Volume 40.

Core service for managing enterprise integrations, connections,
tokens, health monitoring, and lifecycle management.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ─── Constants ─────────────────────────────────────────────────────────────

CONNECTION_STATES = [
    "created", "connected", "active", "degraded",
    "reauthorization_required", "disconnected", "revoked",
]

SYNC_STATES = ["pending", "running", "completed", "failed", "cancelled"]

PROVIDER_CATEGORIES = {
    "github": "source_control",
    "gitlab": "source_control",
    "bitbucket": "source_control",
    "jira": "project_management",
    "slack": "communication",
    "microsoft_teams": "communication",
    "google_workspace": "identity",
    "microsoft_365": "identity",
    "oidc": "identity",
    "saml": "identity",
    "scim": "identity",
}


# ─── Models ────────────────────────────────────────────────────────────────

class IntegrationRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    organization_id: str
    name: str
    provider: str
    category: str = ""
    status: str = "created"
    description: str = ""
    version: str = "1.0.0"
    owner_id: str = ""
    scopes_requested: list[str] = Field(default_factory=list)
    scopes_granted: list[str] = Field(default_factory=list)
    health_status: str = "unknown"
    config: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ConnectionRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    integration_id: str
    organization_id: str
    provider: str
    status: str = "created"
    access_token_ref: str = ""
    refresh_token_ref: str = ""
    token_type: str = "Bearer"
    expires_at: Optional[str] = None
    scopes: list[str] = Field(default_factory=list)
    provider_user_id: str = ""
    provider_username: str = ""
    provider_email: str = ""
    device_info: dict[str, Any] = Field(default_factory=dict)
    error_message: str = ""
    retry_count: int = 0
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SyncJobRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    integration_id: str
    organization_id: str
    sync_type: str
    status: str = "pending"
    trigger: str = "manual"
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_ms: float = 0.0
    records_processed: int = 0
    records_created: int = 0
    records_updated: int = 0
    records_deleted: int = 0
    error_message: str = ""
    idempotency_key: Optional[str] = None


class HealthRecord(BaseModel):
    provider: str
    organization_id: str
    authentication_ok: bool = True
    api_available: bool = True
    rate_limit_remaining: int = 0
    webhook_delivery_ok: bool = True
    sync_healthy: bool = True
    token_expiring_soon: bool = False
    token_expires_at: Optional[str] = None
    last_error: str = ""
    checked_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ─── Token Management ─────────────────────────────────────────────────────

class TokenManager:
    """Secure token storage reference management.

    Tokens are stored as HMAC-SHA256 hashes for comparison.
    The actual token values are never stored in plain text.
    """

    @staticmethod
    def generate_token() -> str:
        return f"nf_{secrets.token_urlsafe(32)}"

    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def generate_state(nonce_len: int = 32) -> str:
        return secrets.token_urlsafe(nonce_len)

    @staticmethod
    def verify_state(state: str, expected: str) -> bool:
        return hmac.compare_digest(state, expected)

    @staticmethod
    def create_oauth_state(user_id: str, provider: str, redirect_uri: str) -> dict[str, Any]:
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(16)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        return {
            "state": state,
            "nonce": nonce,
            "user_id": user_id,
            "provider": provider,
            "redirect_uri": redirect_uri,
            "expires_at": expires_at.isoformat(),
        }

    @staticmethod
    def mask_token(token: str) -> str:
        if len(token) <= 8:
            return "***"
        return f"{token[:4]}...{token[-4:]}"

    @staticmethod
    def is_token_expiring(expires_at: str, buffer_minutes: int = 30) -> bool:
        try:
            exp = datetime.fromisoformat(expires_at)
            return datetime.now(timezone.utc) >= (exp - timedelta(minutes=buffer_minutes))
        except (ValueError, TypeError):
            return True


# ─── Signature Verification ───────────────────────────────────────────────

class SignatureVerifier:
    """HMAC-SHA256 signature verification for webhooks."""

    @staticmethod
    def sign(payload: bytes, secret: str) -> str:
        return hmac.new(
            secret.encode("utf-8"), payload, hashlib.sha256
        ).hexdigest()

    @staticmethod
    def verify(payload: bytes, signature: str, secret: str) -> bool:
        expected = hmac.new(
            secret.encode("utf-8"), payload, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(signature, expected)

    @staticmethod
    def verify_github_signature(payload: bytes, signature: str, secret: str) -> bool:
        if signature.startswith("sha256="):
            signature = signature[7:]
        return SignatureVerifier.verify(payload, signature, secret)

    @staticmethod
    def verify_gitlab_token(token: str, secret: str) -> bool:
        return hmac.compare_digest(token, secret)


# ─── Rate Limiter ──────────────────────────────────────────────────────────

class ProviderRateLimiter:
    """Provider-aware rate limiting with backoff."""

    PROVIDER_LIMITS = {
        "github": {"requests_per_hour": 5000, "search_per_minute": 30},
        "gitlab": {"requests_per_minute": 60, "search_per_second": 5},
        "bitbucket": {"requests_per_hour": 1000},
        "jira": {"requests_per_minute": 100},
        "slack": {"requests_per_minute": 50},
        "microsoft_teams": {"requests_per_minute": 60},
    }

    def __init__(self) -> None:
        self._counters: dict[str, list[float]] = {}

    def check_rate_limit(self, provider: str, endpoint_group: str = "default") -> dict[str, Any]:
        limits = self.PROVIDER_LIMITS.get(provider, {"requests_per_minute": 60})
        key = f"{provider}:{endpoint_group}"
        now = datetime.now(timezone.utc).timestamp()
        window = now - 60

        if key not in self._counters:
            self._counters[key] = []

        self._counters[key] = [t for t in self._counters[key] if t > window]
        current = len(self._counters[key])
        limit = limits.get("requests_per_minute", 60)

        allowed = current < limit
        if allowed:
            self._counters[key].append(now)

        return {
            "allowed": allowed,
            "current": current,
            "limit": limit,
            "retry_after_seconds": 60 if not allowed else 0,
        }

    def backoff_seconds(self, provider: str, attempt: int) -> float:
        base = 30.0
        max_backoff = 300.0
        return min(base * (2 ** attempt), max_backoff)


# ─── Event Normalization ──────────────────────────────────────────────────

class EventNormalizer:
    """Normalize provider-specific events into internal event format."""

    PROVIDER_EVENT_MAP = {
        "github": {
            "push": "external_repository_changed",
            "pull_request": "pull_request_changed",
            "issues": "issue_changed",
            "pull_request_review": "pull_request_reviewed",
            "installation": "integration_changed",
            "repository": "external_repository_changed",
        },
        "gitlab": {
            "push_hooks": "external_repository_changed",
            "merge_request_hooks": "pull_request_changed",
            "note_hooks": "issue_changed",
            "pipeline_hooks": "pipeline_changed",
        },
        "bitbucket": {
            "repo:push": "external_repository_changed",
            "pullrequest:created": "pull_request_changed",
            "pullrequest:updated": "pull_request_changed",
            "issue:created": "issue_changed",
        },
        "jira": {
            "jira:issue_created": "issue_changed",
            "jira:issue_updated": "issue_changed",
            "comment_created": "issue_comment_changed",
        },
        "slack": {
            "message": "message_received",
            "reaction_added": "reaction_received",
            "app_mention": "mention_received",
        },
        "microsoft_teams": {
            "message": "message_received",
        },
    }

    @staticmethod
    def normalize(
        provider: str,
        provider_event_type: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        event_map = EventNormalizer.PROVIDER_EVENT_MAP.get(provider, {})
        internal_type = event_map.get(provider_event_type, f"{provider}.{provider_event_type}")

        return {
            "event_type": internal_type,
            "source": provider,
            "provider_event_type": provider_event_type,
            "payload": payload,
            "normalized_at": datetime.now(timezone.utc).isoformat(),
            "idempotency_key": EventNormalizer._make_idempotency_key(provider, provider_event_type, payload),
        }

    @staticmethod
    def _make_idempotency_key(provider: str, event_type: str, payload: dict) -> str:
        parts = [provider, event_type]
        for key in ("id", "number", "action", "ref"):
            if key in payload:
                parts.append(str(payload[key]))
        if "after" in payload:
            parts.append(str(payload["after"]))
        blob = ":".join(parts)
        return hashlib.sha256(blob.encode()).hexdigest()[:24]


# ─── Integration Registry Service ─────────────────────────────────────────

class IntegrationRegistryService:
    """In-memory integration registry with full lifecycle management."""

    _instance: Optional["IntegrationRegistryService"] = None

    def __new__(cls) -> "IntegrationRegistryService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._integrations: dict[str, IntegrationRecord] = {}
        self._connections: dict[str, ConnectionRecord] = {}
        self._sync_jobs: dict[str, SyncJobRecord] = {}
        self._health: dict[str, HealthRecord] = {}
        self._events: list[dict[str, Any]] = []
        self._oauth_states: dict[str, dict[str, Any]] = {}
        self._rate_limiters: dict[str, ProviderRateLimiter] = {}
        self._token_manager = TokenManager()
        self._normalizer = EventNormalizer()
        self._initialized = True

    def reset(self) -> None:
        self._integrations.clear()
        self._connections.clear()
        self._sync_jobs.clear()
        self._health.clear()
        self._events.clear()
        self._oauth_states.clear()

    # ── Integration CRUD ────────────────────────────────────────────────

    def create_integration(
        self,
        organization_id: str,
        name: str,
        provider: str,
        category: str = "",
        description: str = "",
        owner_id: str = "",
        scopes_requested: list[str] | None = None,
        config: dict[str, Any] | None = None,
    ) -> IntegrationRecord:
        if not category:
            category = PROVIDER_CATEGORIES.get(provider, "custom")
        record = IntegrationRecord(
            organization_id=organization_id,
            name=name,
            provider=provider,
            category=category,
            description=description,
            owner_id=owner_id,
            scopes_requested=scopes_requested or [],
            config=config or {},
        )
        self._integrations[record.id] = record
        return record

    def get_integration(self, integration_id: str) -> Optional[IntegrationRecord]:
        return self._integrations.get(integration_id)

    def list_integrations(
        self,
        organization_id: str | None = None,
        provider: str | None = None,
        category: str | None = None,
    ) -> list[IntegrationRecord]:
        results = list(self._integrations.values())
        if organization_id:
            results = [i for i in results if i.organization_id == organization_id]
        if provider:
            results = [i for i in results if i.provider == provider]
        if category:
            results = [i for i in results if i.category == category]
        return results

    def update_integration(
        self,
        integration_id: str,
        name: str | None = None,
        status: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> Optional[IntegrationRecord]:
        rec = self._integrations.get(integration_id)
        if not rec:
            return None
        if name is not None:
            rec.name = name
        if status is not None:
            rec.status = status
        if config is not None:
            rec.config = config
        rec.updated_at = datetime.now(timezone.utc).isoformat()
        return rec

    def delete_integration(self, integration_id: str) -> bool:
        if integration_id not in self._integrations:
            return False
        del self._integrations[integration_id]
        to_remove = [c_id for c_id, c in self._connections.items() if c.integration_id == integration_id]
        for c_id in to_remove:
            del self._connections[c_id]
        return True

    # ── Connection Lifecycle ────────────────────────────────────────────

    def create_connection(
        self,
        integration_id: str,
        organization_id: str,
        provider: str,
    ) -> Optional[ConnectionRecord]:
        integration = self._integrations.get(integration_id)
        if not integration:
            return None
        conn = ConnectionRecord(
            integration_id=integration_id,
            organization_id=organization_id,
            provider=provider,
            status="created",
        )
        self._connections[conn.id] = conn
        integration.status = "connected"
        integration.updated_at = datetime.now(timezone.utc).isoformat()
        return conn

    def activate_connection(
        self,
        connection_id: str,
        access_token: str = "",
        refresh_token: str = "",
        scopes: list[str] | None = None,
        provider_user_id: str = "",
        provider_username: str = "",
        provider_email: str = "",
        expires_in_seconds: int = 0,
    ) -> Optional[ConnectionRecord]:
        conn = self._connections.get(connection_id)
        if not conn:
            return None
        conn.access_token_ref = self._token_manager.hash_token(access_token) if access_token else ""
        conn.refresh_token_ref = self._token_manager.hash_token(refresh_token) if refresh_token else ""
        conn.scopes = scopes or []
        conn.provider_user_id = provider_user_id
        conn.provider_username = provider_username
        conn.provider_email = provider_email
        if expires_in_seconds > 0:
            conn.expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)).isoformat()
        conn.status = "active"
        conn.updated_at = datetime.now(timezone.utc).isoformat()

        integration = self._integrations.get(conn.integration_id)
        if integration:
            integration.status = "active"
            integration.scopes_granted = scopes or []
            integration.updated_at = datetime.now(timezone.utc).isoformat()
        return conn

    def get_connection(self, connection_id: str) -> Optional[ConnectionRecord]:
        return self._connections.get(connection_id)

    def list_connections(
        self,
        integration_id: str | None = None,
        organization_id: str | None = None,
    ) -> list[ConnectionRecord]:
        results = list(self._connections.values())
        if integration_id:
            results = [c for c in results if c.integration_id == integration_id]
        if organization_id:
            results = [c for c in results if c.organization_id == organization_id]
        return results

    def revoke_connection(self, connection_id: str) -> Optional[ConnectionRecord]:
        conn = self._connections.get(connection_id)
        if not conn:
            return None
        conn.status = "revoked"
        conn.access_token_ref = ""
        conn.refresh_token_ref = ""
        conn.updated_at = datetime.now(timezone.utc).isoformat()

        integration = self._integrations.get(conn.integration_id)
        if integration:
            integration.status = "disconnected"
            integration.updated_at = datetime.now(timezone.utc).isoformat()
        return conn

    def refresh_connection(self, connection_id: str) -> Optional[ConnectionRecord]:
        conn = self._connections.get(connection_id)
        if not conn:
            return None
        if conn.status not in ("active", "degraded"):
            return None
        conn.last_rotated_at = datetime.now(timezone.utc).isoformat()
        conn.updated_at = datetime.now(timezone.utc).isoformat()
        return conn

    # ── OAuth State Management ──────────────────────────────────────────

    def create_oauth_state(
        self,
        user_id: str,
        provider: str,
        redirect_uri: str,
    ) -> dict[str, Any]:
        state_data = self._token_manager.create_oauth_state(user_id, provider, redirect_uri)
        self._oauth_states[state_data["state"]] = state_data
        return state_data

    def validate_oauth_state(self, state: str) -> Optional[dict[str, Any]]:
        state_data = self._oauth_states.pop(state, None)
        if not state_data:
            return None
        expires_at = datetime.fromisoformat(state_data["expires_at"])
        if datetime.now(timezone.utc) > expires_at:
            return None
        return state_data

    # ── Sync Jobs ───────────────────────────────────────────────────────

    def create_sync_job(
        self,
        integration_id: str,
        organization_id: str,
        sync_type: str,
        trigger: str = "manual",
        idempotency_key: str | None = None,
    ) -> SyncJobRecord:
        if idempotency_key:
            for job in self._sync_jobs.values():
                if job.idempotency_key == idempotency_key and job.integration_id == integration_id:
                    return job
        job = SyncJobRecord(
            integration_id=integration_id,
            organization_id=organization_id,
            sync_type=sync_type,
            trigger=trigger,
            idempotency_key=idempotency_key,
        )
        self._sync_jobs[job.id] = job
        return job

    def start_sync_job(self, job_id: str) -> Optional[SyncJobRecord]:
        job = self._sync_jobs.get(job_id)
        if not job or job.status != "pending":
            return None
        job.status = "running"
        job.started_at = datetime.now(timezone.utc).isoformat()
        return job

    def complete_sync_job(
        self,
        job_id: str,
        records_processed: int = 0,
        records_created: int = 0,
        records_updated: int = 0,
        records_deleted: int = 0,
    ) -> Optional[SyncJobRecord]:
        job = self._sync_jobs.get(job_id)
        if not job or job.status != "running":
            return None
        job.status = "completed"
        job.completed_at = datetime.now(timezone.utc).isoformat()
        if job.started_at:
            started = datetime.fromisoformat(job.started_at)
            completed = datetime.fromisoformat(job.completed_at)
            job.duration_ms = (completed - started).total_seconds() * 1000
        job.records_processed = records_processed
        job.records_created = records_created
        job.records_updated = records_updated
        job.records_deleted = records_deleted
        return job

    def fail_sync_job(self, job_id: str, error: str = "") -> Optional[SyncJobRecord]:
        job = self._sync_jobs.get(job_id)
        if not job:
            return None
        job.status = "failed"
        job.completed_at = datetime.now(timezone.utc).isoformat()
        job.error_message = error
        return job

    def get_sync_job(self, job_id: str) -> Optional[SyncJobRecord]:
        return self._sync_jobs.get(job_id)

    def list_sync_jobs(
        self,
        integration_id: str | None = None,
        status: str | None = None,
    ) -> list[SyncJobRecord]:
        results = list(self._sync_jobs.values())
        if integration_id:
            results = [j for j in results if j.integration_id == integration_id]
        if status:
            results = [j for j in results if j.status == status]
        return sorted(results, key=lambda j: j.created_at, reverse=True)

    # ── Health Monitoring ───────────────────────────────────────────────

    def update_health(
        self,
        provider: str,
        organization_id: str,
        **kwargs: Any,
    ) -> HealthRecord:
        key = f"{provider}:{organization_id}"
        existing = self._health.get(key)
        if existing:
            for k, v in kwargs.items():
                if hasattr(existing, k):
                    setattr(existing, k, v)
            existing.checked_at = datetime.now(timezone.utc).isoformat()
            return existing
        record = HealthRecord(provider=provider, organization_id=organization_id, **kwargs)
        self._health[key] = record
        return record

    def get_health(self, provider: str, organization_id: str) -> Optional[HealthRecord]:
        return self._health.get(f"{provider}:{organization_id}")

    def list_health(self, organization_id: str | None = None) -> list[HealthRecord]:
        results = list(self._health.values())
        if organization_id:
            results = [h for h in results if h.organization_id == organization_id]
        return results

    # ── Events ──────────────────────────────────────────────────────────

    def record_event(
        self,
        provider: str,
        provider_event_type: str,
        payload: dict[str, Any],
        integration_id: str = "",
        organization_id: str = "",
    ) -> dict[str, Any]:
        normalized = self._normalizer.normalize(provider, provider_event_type, payload)
        normalized["integration_id"] = integration_id
        normalized["organization_id"] = organization_id
        self._events.append(normalized)
        return normalized

    def get_events(
        self,
        integration_id: str | None = None,
        organization_id: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        results = list(self._events)
        if integration_id:
            results = [e for e in results if e.get("integration_id") == integration_id]
        if organization_id:
            results = [e for e in results if e.get("organization_id") == organization_id]
        if event_type:
            results = [e for e in results if e.get("event_type") == event_type]
        return results[-limit:]

    # ── Rate Limiting ───────────────────────────────────────────────────

    def check_rate_limit(self, provider: str, endpoint_group: str = "default") -> dict[str, Any]:
        if provider not in self._rate_limiters:
            self._rate_limiters[provider] = ProviderRateLimiter()
        return self._rate_limiters[provider].check_rate_limit(provider, endpoint_group)

    # ── Aggregate Metrics ───────────────────────────────────────────────

    def get_metrics(self, organization_id: str | None = None) -> dict[str, Any]:
        integrations = self.list_integrations(organization_id)
        connections = self.list_connections(organization_id=organization_id)
        return {
            "total_integrations": len(integrations),
            "active_integrations": sum(1 for i in integrations if i.status == "active"),
            "total_connections": len(connections),
            "active_connections": sum(1 for c in connections if c.status == "active"),
            "revoked_connections": sum(1 for c in connections if c.status == "revoked"),
            "total_sync_jobs": len(self.list_sync_jobs()),
            "providers": list({i.provider for i in integrations}),
        }
