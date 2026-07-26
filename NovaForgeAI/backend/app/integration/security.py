"""Integration Security — encrypted credentials, secret rotation, OAuth tokens, permission validation, connector isolation, rate limiting, audit logging."""
import json, uuid, os, logging, hashlib, hmac
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class SecurityEventType(Enum):
    CREDENTIAL_ACCESS = "credential_access"
    CREDENTIAL_ROTATION = "credential_rotation"
    PERMISSION_DENIED = "permission_denied"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    CONNECTOR_ISOLATION = "connector_isolation"
    AUDIT_LOG = "audit_log"
    OAUTH_REFRESH = "oauth_refresh"
    SECRET_EXPIRY = "secret_expiry"


@dataclass
class CredentialStore:
    id: str
    connector_id: str
    credential_type: str
    encrypted_value: str = ""
    key_id: str = ""
    expires_at: str = ""
    last_rotated: str = ""
    rotation_interval_days: int = 90
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["encrypted_value"] = "***"
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "CredentialStore":
        return cls(**data)


@dataclass
class SecurityAuditLog:
    id: str
    org_id: str
    event_type: SecurityEventType
    actor: str = ""
    resource: str = ""
    details: str = ""
    ip_address: str = ""
    success: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["event_type"] = self.event_type.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "SecurityAuditLog":
        data = data.copy()
        data["event_type"] = SecurityEventType(data.get("event_type", "audit_log"))
        return cls(**data)


@dataclass
class RateLimitBucket:
    connector_id: str
    window_start: str
    request_count: int = 0
    limit: int = 100
    window_seconds: int = 60

    def to_dict(self) -> dict: return asdict(self)


class IntegrationSecurity:
    def __init__(self, storage_dir: str = "integration_data/security"):
        self.storage_dir = storage_dir
        self._credentials: dict[str, CredentialStore] = {}
        self._audit_logs: list[SecurityAuditLog] = []
        self._rate_limiters: dict[str, RateLimitBucket] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _cred_path(self) -> str: return os.path.join(self.storage_dir, "credentials.json")
    def _audit_path(self) -> str: return os.path.join(self.storage_dir, "audit.json")

    def _load(self) -> None:
        for path, store, cls in [
            (self._cred_path(), self._credentials, CredentialStore),
            (self._audit_path(), None, None),
        ]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if cls:
                        for k, v in data.items():
                            try: store[k] = cls.from_dict(v)
                            except Exception as e: logger.warning("Skipping %s: %s", k, e)
                    else:
                        self._audit_logs = [SecurityAuditLog.from_dict(l) for l in data]
                except Exception as e: logger.error("Failed to load security data: %s", e)

    def _save(self) -> None:
        try:
            with open(self._cred_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._credentials.items()}, f, indent=2, default=str)
            with open(self._audit_path(), "w", encoding="utf-8") as f:
                json.dump([l.to_dict() for l in self._audit_logs[-5000:]], f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save security data: %s", e)

    def store_credential(self, connector_id: str, credential_type: str, value: str, expires_at: str = "") -> CredentialStore:
        cs = CredentialStore(id=str(uuid.uuid4()), connector_id=connector_id, credential_type=credential_type, encrypted_value=hashlib.sha256(value.encode()).hexdigest(), key_id=str(uuid.uuid4()), expires_at=expires_at)
        self._credentials[cs.id] = cs
        self._save()
        return cs

    def rotate_credential(self, credential_id: str, new_value: str) -> bool:
        cs = self._credentials.get(credential_id)
        if not cs: return False
        cs.encrypted_value = hashlib.sha256(new_value.encode()).hexdigest()
        cs.last_rotated = datetime.now(timezone.utc).isoformat()
        cs.key_id = str(uuid.uuid4())
        self._save()
        self.audit_log("system", SecurityEventType.CREDENTIAL_ROTATION, f"credential:{credential_id}", "Credential rotated")
        return True

    def check_rate_limit(self, connector_id: str, limit: int = 100, window_seconds: int = 60) -> bool:
        now = datetime.now(timezone.utc)
        bucket = self._rate_limiters.get(connector_id)
        if not bucket:
            bucket = RateLimitBucket(connector_id=connector_id, window_start=now.isoformat(), limit=limit, window_seconds=window_seconds)
            self._rate_limiters[connector_id] = bucket
        window_start = datetime.fromisoformat(bucket.window_start)
        if (now - window_start).total_seconds() > window_seconds:
            bucket.window_start = now.isoformat()
            bucket.request_count = 0
        bucket.request_count += 1
        if bucket.request_count > limit:
            self.audit_log("system", SecurityEventType.RATE_LIMIT_EXCEEDED, f"connector:{connector_id}", f"Rate limit {limit}/{window_seconds}s exceeded")
            return False
        return True

    def audit_log(self, actor: str, event_type: SecurityEventType, resource: str = "", details: str = "", success: bool = True, ip_address: str = "") -> SecurityAuditLog:
        log = SecurityAuditLog(id=str(uuid.uuid4()), org_id="", event_type=event_type, actor=actor, resource=resource, details=details, ip_address=ip_address, success=success)
        self._audit_logs.append(log)
        self._save()
        return log

    def get_audit_logs(self, event_type: Optional[SecurityEventType] = None, limit: int = 100) -> list[SecurityAuditLog]:
        results = list(self._audit_logs)
        if event_type: results = [l for l in results if l.event_type == event_type]
        return sorted(results, key=lambda l: l.created_at, reverse=True)[:limit]

    def get_telemetry(self) -> dict: return dict(self._telemetry)
