"""Session service — session lifecycle, expiration, revocation, tracking."""
from __future__ import annotations
import uuid
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional
from app.iam.config import get_iam_config


class SessionService:
    def __init__(self):
        self._sessions: dict[str, dict] = {}
        self._config = get_iam_config()

    def create(self, user_id: str, organization_id: Optional[str] = None, ip_address: str = "", user_agent: str = "", auth_method: str = "password", device_fingerprint: str = "") -> dict:
        self._enforce_max_concurrent(user_id)
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        session = {"id": session_id, "user_id": user_id, "organization_id": organization_id, "session_token": secrets.token_urlsafe(64), "refresh_token": secrets.token_urlsafe(64), "ip_address": ip_address, "user_agent": user_agent, "device_fingerprint": device_fingerprint, "auth_method": auth_method, "is_active": True, "expires_at": (now + timedelta(hours=self._config.session_absolute_hours)).isoformat(), "idle_expires_at": (now + timedelta(minutes=self._config.session_idle_minutes)).isoformat(), "last_activity_at": now.isoformat(), "created_at": now.isoformat()}
        self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> Optional[dict]:
        session = self._sessions.get(session_id)
        if session and self._is_expired(session):
            session["is_active"] = False
            session["revoked_at"] = datetime.now(timezone.utc).isoformat()
            session["revocation_reason"] = "expired"
        return session

    def validate(self, session_id: str) -> dict:
        session = self.get(session_id)
        if not session:
            return {"valid": False, "reason": "session_not_found"}
        if not session["is_active"]:
            return {"valid": False, "reason": "session_inactive"}
        if self._is_expired(session):
            session["is_active"] = False
            return {"valid": False, "reason": "session_expired"}
        return {"valid": True, "session": session}

    def refresh(self, session_id: str) -> Optional[dict]:
        session = self.get(session_id)
        if not session or not session["is_active"]:
            return None
        now = datetime.now(timezone.utc)
        session["refresh_token"] = secrets.token_urlsafe(64)
        session["last_activity_at"] = now.isoformat()
        session["idle_expires_at"] = (now + timedelta(minutes=self._config.session_idle_minutes)).isoformat()
        return session

    def revoke(self, session_id: str, reason: str = "user_request") -> bool:
        session = self._sessions.get(session_id)
        if not session:
            return False
        session["is_active"] = False
        session["revoked_at"] = datetime.now(timezone.utc).isoformat()
        session["revocation_reason"] = reason
        return True

    def revoke_all_for_user(self, user_id: str, reason: str = "global_revoke") -> int:
        count = 0
        for session in self._sessions.values():
            if session["user_id"] == user_id and session["is_active"]:
                session["is_active"] = False
                session["revoked_at"] = datetime.now(timezone.utc).isoformat()
                session["revocation_reason"] = reason
                count += 1
        return count

    def revoke_all_for_org(self, org_id: str, reason: str = "org_suspend") -> int:
        count = 0
        for session in self._sessions.values():
            if session.get("organization_id") == org_id and session["is_active"]:
                session["is_active"] = False
                session["revoked_at"] = datetime.now(timezone.utc).isoformat()
                session["revocation_reason"] = reason
                count += 1
        return count

    def list_for_user(self, user_id: str, active_only: bool = True) -> list[dict]:
        sessions = [s for s in self._sessions.values() if s["user_id"] == user_id]
        if active_only:
            sessions = [s for s in sessions if s["is_active"] and not self._is_expired(s)]
        return sessions

    def cleanup_expired(self) -> int:
        count = 0
        for session in list(self._sessions.values()):
            if self._is_expired(session) and session["is_active"]:
                session["is_active"] = False
                session["revoked_at"] = datetime.now(timezone.utc).isoformat()
                session["revocation_reason"] = "cleanup_expired"
                count += 1
        return count

    def touch(self, session_id: str) -> bool:
        session = self._sessions.get(session_id)
        if not session or not session["is_active"]:
            return False
        now = datetime.now(timezone.utc)
        session["last_activity_at"] = now.isoformat()
        session["idle_expires_at"] = (now + timedelta(minutes=self._config.session_idle_minutes)).isoformat()
        return True

    def _enforce_max_concurrent(self, user_id: str) -> None:
        active = [s for s in self._sessions.values() if s["user_id"] == user_id and s["is_active"]]
        if len(active) >= self._config.session_max_concurrent:
            oldest = min(active, key=lambda s: s["created_at"])
            oldest["is_active"] = False
            oldest["revoked_at"] = datetime.now(timezone.utc).isoformat()
            oldest["revocation_reason"] = "max_concurrent_exceeded"

    def _is_expired(self, session: dict) -> bool:
        now = datetime.now(timezone.utc)
        try:
            expires = datetime.fromisoformat(session["expires_at"])
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if now > expires:
                return True
        except (ValueError, KeyError):
            pass
        try:
            idle_expires = datetime.fromisoformat(session["idle_expires_at"])
            if idle_expires.tzinfo is None:
                idle_expires = idle_expires.replace(tzinfo=timezone.utc)
            if now > idle_expires:
                return True
        except (ValueError, KeyError):
            pass
        return False

    def get_stats(self, user_id: Optional[str] = None) -> dict:
        sessions = list(self._sessions.values())
        if user_id:
            sessions = [s for s in sessions if s["user_id"] == user_id]
        active = [s for s in sessions if s["is_active"]]
        return {"total": len(sessions), "active": len(active), "expired": len(sessions) - len(active)}

    def terminate_on_suspension(self, user_id: str) -> int:
        return self.revoke_all_for_user(user_id, reason="account_suspended")


session_service = SessionService()
