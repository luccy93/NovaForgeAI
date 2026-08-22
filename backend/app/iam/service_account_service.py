"""Service account service — create, rotate, scope, disable, audit."""
from __future__ import annotations
import uuid
import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional
from app.iam.config import get_iam_config


class ServiceAccountService:
    def __init__(self):
        self._service_accounts: dict[str, dict] = {}
        self._client_secrets: dict[str, str] = {}
        self._config = get_iam_config()

    def create(self, org_id: str, name: str, description: str = "", scopes: Optional[list[str]] = None, expires_in_days: Optional[int] = None, created_by: str = "", max_usage: Optional[int] = None) -> dict:
        org_accounts = [sa for sa in self._service_accounts.values() if sa["organization_id"] == org_id and sa["is_active"]]
        if len(org_accounts) >= self._config.service_account_max_per_org:
            return {"error": f"Maximum service accounts ({self._config.service_account_max_per_org}) exceeded for organization"}
        client_id = f"nf-sa-{secrets.token_hex(16)}"
        client_secret = secrets.token_urlsafe(48)
        secret_hash = hashlib.sha256(client_secret.encode()).hexdigest()
        sa_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        expires_at = None
        if expires_in_days:
            expires_at = (now + timedelta(days=expires_in_days)).isoformat()
        sa = {"id": sa_id, "organization_id": org_id, "name": name, "description": description, "client_id": client_id, "client_secret_hash": secret_hash, "scopes": scopes or [], "is_active": True, "expires_at": expires_at, "last_used_at": None, "last_rotated_at": None, "max_usage": max_usage, "current_usage": 0, "created_by": created_by, "created_at": now.isoformat(), "updated_at": now.isoformat()}
        self._service_accounts[sa_id] = sa
        self._client_secrets[client_id] = secret_hash
        return {"sa_data": sa, "client_secret": client_secret, "warning": "Store this secret securely. It will not be shown again."}

    def validate(self, client_id: str, client_secret: str) -> dict:
        sa = None
        for s in self._service_accounts.values():
            if s["client_id"] == client_id:
                sa = s
                break
        if not sa:
            return {"valid": False, "reason": "service_account_not_found"}
        if not sa["is_active"]:
            return {"valid": False, "reason": "service_account_inactive"}
        if sa.get("expires_at"):
            expires = datetime.fromisoformat(sa["expires_at"])
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > expires:
                sa["is_active"] = False
                return {"valid": False, "reason": "service_account_expired"}
        if sa.get("max_usage") and sa["current_usage"] >= sa["max_usage"]:
            return {"valid": False, "reason": "usage_limit_reached"}
        secret_hash = hashlib.sha256(client_secret.encode()).hexdigest()
        if secret_hash != sa["client_secret_hash"]:
            return {"valid": False, "reason": "invalid_secret"}
        sa["last_used_at"] = datetime.now(timezone.utc).isoformat()
        sa["current_usage"] += 1
        return {"valid": True, "service_account": sa}

    def get(self, sa_id: str) -> Optional[dict]:
        return self._service_accounts.get(sa_id)

    def list_for_org(self, org_id: str, active_only: bool = True) -> list[dict]:
        accounts = [sa for sa in self._service_accounts.values() if sa["organization_id"] == org_id]
        if active_only:
            accounts = [sa for sa in accounts if sa["is_active"]]
        return accounts

    def rotate(self, sa_id: str, reason: str = "rotation") -> dict:
        sa = self._service_accounts.get(sa_id)
        if not sa or not sa["is_active"]:
            return {"error": "Service account not found or inactive"}
        client_secret = secrets.token_urlsafe(48)
        secret_hash = hashlib.sha256(client_secret.encode()).hexdigest()
        sa["client_secret_hash"] = secret_hash
        sa["last_rotated_at"] = datetime.now(timezone.utc).isoformat()
        sa["updated_at"] = datetime.now(timezone.utc).isoformat()
        return {"client_secret": client_secret, "warning": "Store this secret securely. It will not be shown again."}

    def disable(self, sa_id: str, reason: str = "disabled") -> bool:
        sa = self._service_accounts.get(sa_id)
        if not sa:
            return False
        sa["is_active"] = False
        sa["disabled_at"] = datetime.now(timezone.utc).isoformat()
        sa["disabled_reason"] = reason
        sa["updated_at"] = datetime.now(timezone.utc).isoformat()
        return True

    def delete(self, sa_id: str) -> bool:
        return self._service_accounts.pop(sa_id, None) is not None

    def update_scopes(self, sa_id: str, scopes: list[str]) -> Optional[dict]:
        sa = self._service_accounts.get(sa_id)
        if not sa:
            return None
        sa["scopes"] = scopes
        sa["updated_at"] = datetime.now(timezone.utc).isoformat()
        return sa

    def cleanup_expired(self) -> int:
        count = 0
        now = datetime.now(timezone.utc)
        for sa in self._service_accounts.values():
            if sa["is_active"] and sa.get("expires_at"):
                expires = datetime.fromisoformat(sa["expires_at"])
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=timezone.utc)
                if now > expires:
                    sa["is_active"] = False
                    count += 1
        return count

    def get_stats(self, org_id: str) -> dict:
        accounts = self.list_for_org(org_id, active_only=False)
        return {"total": len(accounts), "active": sum(1 for a in accounts if a["is_active"]), "expired": sum(1 for a in accounts if not a["is_active"])}


service_account_service = ServiceAccountService()
