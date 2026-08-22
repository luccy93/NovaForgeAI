"""API key service — creation, rotation, revocation, scope management."""
from __future__ import annotations
import uuid
import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional
from app.iam.config import get_iam_config


class APIKeyService:
    def __init__(self):
        self._api_keys: dict[str, dict] = {}
        self._key_hashes: dict[str, str] = {}
        self._config = get_iam_config()

    def create(self, org_id: str, user_id: str, name: str, scopes: Optional[list[str]] = None, expires_in_days: Optional[int] = None) -> dict:
        user_keys = [k for k in self._api_keys.values() if k["user_id"] == user_id and k["is_active"]]
        if len(user_keys) >= self._config.api_key_max_per_user:
            return {"error": f"Maximum API keys ({self._config.api_key_max_per_user}) exceeded"}
        raw_key = f"nf_{secrets.token_urlsafe(48)}"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        key_prefix = raw_key[:10]
        key_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        expires_at = None
        if expires_in_days:
            expires_at = (now + timedelta(days=expires_in_days)).isoformat()
        elif self._config.max_api_key_expiry_days:
            expires_at = (now + timedelta(days=self._config.max_api_key_expiry_days)).isoformat()
        key_data = {"id": key_id, "organization_id": org_id, "user_id": user_id, "name": name, "key_hash": key_hash, "key_prefix": key_prefix, "scopes": scopes or [], "is_active": True, "expires_at": expires_at, "created_at": now.isoformat(), "last_used_at": None, "revoked_at": None, "revocation_reason": None, "last_rotated_at": None}
        self._api_keys[key_id] = key_data
        self._key_hashes[key_hash] = key_id
        return {"key_data": key_data, "raw_key": raw_key, "warning": "Store this key securely. It will not be shown again."}

    def validate(self, raw_key: str) -> dict:
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        key_id = self._key_hashes.get(key_hash)
        if not key_id:
            return {"valid": False, "reason": "key_not_found"}
        key = self._api_keys.get(key_id)
        if not key:
            return {"valid": False, "reason": "key_not_found"}
        if not key["is_active"]:
            return {"valid": False, "reason": "key_inactive"}
        if key.get("expires_at"):
            expires = datetime.fromisoformat(key["expires_at"])
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > expires:
                key["is_active"] = False
                return {"valid": False, "reason": "key_expired"}
        key["last_used_at"] = datetime.now(timezone.utc).isoformat()
        return {"valid": True, "key": key}

    def get(self, key_id: str) -> Optional[dict]:
        return self._api_keys.get(key_id)

    def list_for_user(self, user_id: str) -> list[dict]:
        return [k for k in self._api_keys.values() if k["user_id"] == user_id]

    def list_for_org(self, org_id: str) -> list[dict]:
        return [k for k in self._api_keys.values() if k["organization_id"] == org_id]

    def revoke(self, key_id: str, reason: str = "user_request") -> bool:
        key = self._api_keys.get(key_id)
        if not key:
            return False
        key["is_active"] = False
        key["revoked_at"] = datetime.now(timezone.utc).isoformat()
        key["revocation_reason"] = reason
        return True

    def revoke_all_for_user(self, user_id: str, reason: str = "global_revoke") -> int:
        count = 0
        for key in self._api_keys.values():
            if key["user_id"] == user_id and key["is_active"]:
                key["is_active"] = False
                key["revoked_at"] = datetime.now(timezone.utc).isoformat()
                key["revocation_reason"] = reason
                count += 1
        return count

    def rotate(self, key_id: str, reason: str = "rotation") -> dict:
        old_key = self._api_keys.get(key_id)
        if not old_key or not old_key["is_active"]:
            return {"error": "Key not found or inactive"}
        self.revoke(key_id, reason=f"rotated: {reason}")
        return self.create(old_key["organization_id"], old_key["user_id"], old_key["name"], old_key["scopes"])

    def cleanup_expired(self) -> int:
        count = 0
        now = datetime.now(timezone.utc)
        for key in self._api_keys.values():
            if key["is_active"] and key.get("expires_at"):
                expires = datetime.fromisoformat(key["expires_at"])
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=timezone.utc)
                if now > expires:
                    key["is_active"] = False
                    key["revoked_at"] = now.isoformat()
                    key["revocation_reason"] = "expired"
                    count += 1
        return count

    def get_stats(self, org_id: Optional[str] = None, user_id: Optional[str] = None) -> dict:
        keys = list(self._api_keys.values())
        if org_id:
            keys = [k for k in keys if k["organization_id"] == org_id]
        if user_id:
            keys = [k for k in keys if k["user_id"] == user_id]
        active = [k for k in keys if k["is_active"]]
        expired = [k for k in active if k.get("expires_at")]
        return {"total": len(keys), "active": len(active), "expired_pending": len(expired)}


api_key_service = APIKeyService()
