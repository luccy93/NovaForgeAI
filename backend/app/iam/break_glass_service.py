"""Break-glass service — emergency access with strong authentication, scope, expiration, audit."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from app.iam.config import get_iam_config


class BreakGlassService:
    def __init__(self):
        self._sessions: dict[str, dict] = {}
        self._config = get_iam_config()
        self._audit_log: list[dict] = []

    def request(self, org_id: str, user_id: str, reason: str, scope: Optional[list[str]] = None, resource_id: str = "", resource_type: str = "", duration_hours: int = 1, mfa_verified: bool = False, approved_by: str = "") -> dict:
        if self._config.break_glass_requires_mfa and not mfa_verified:
            return {"error": "MFA verification required for break-glass access"}
        duration_hours = min(duration_hours, self._config.break_glass_max_hours)
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        session = {"id": session_id, "organization_id": org_id, "user_id": user_id, "reason": reason, "scope": scope or [], "resource_id": resource_id, "resource_type": resource_type, "expires_at": (now + timedelta(hours=duration_hours)).isoformat(), "is_active": True, "mfa_verified": mfa_verified, "approved_by": approved_by, "created_at": now.isoformat()}
        self._sessions[session_id] = session
        self._audit_log.append({"event": "break_glass_started", "session_id": session_id, "user_id": user_id, "org_id": org_id, "reason": reason, "scope": scope, "duration_hours": duration_hours, "time": now.isoformat()})
        return session

    def validate(self, session_id: str) -> dict:
        session = self._sessions.get(session_id)
        if not session:
            return {"valid": False, "reason": "session_not_found"}
        if not session["is_active"]:
            return {"valid": False, "reason": "session_inactive"}
        now = datetime.now(timezone.utc)
        expires = datetime.fromisoformat(session["expires_at"])
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if now > expires:
            session["is_active"] = False
            self._audit_log.append({"event": "break_glass_expired", "session_id": session_id, "time": now.isoformat()})
            return {"valid": False, "reason": "session_expired"}
        return {"valid": True, "session": session}

    def end(self, session_id: str, reason: str = "voluntary") -> bool:
        session = self._sessions.get(session_id)
        if not session:
            return False
        session["is_active"] = False
        session["ended_at"] = datetime.now(timezone.utc).isoformat()
        session["end_reason"] = reason
        self._audit_log.append({"event": "break_glass_ended", "session_id": session_id, "reason": reason, "time": datetime.now(timezone.utc).isoformat()})
        return True

    def cleanup_expired(self) -> int:
        count = 0
        now = datetime.now(timezone.utc)
        for session in self._sessions.values():
            if session["is_active"]:
                expires = datetime.fromisoformat(session["expires_at"])
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=timezone.utc)
                if now > expires:
                    session["is_active"] = False
                    session["ended_at"] = now.isoformat()
                    session["end_reason"] = "auto_expired"
                    self._audit_log.append({"event": "break_glass_expired", "session_id": session["id"], "time": now.isoformat()})
                    count += 1
        return count

    def list_active(self, org_id: Optional[str] = None) -> list[dict]:
        active = [s for s in self._sessions.values() if s["is_active"]]
        if org_id:
            active = [s for s in active if s["organization_id"] == org_id]
        return active

    def list_for_user(self, user_id: str) -> list[dict]:
        return [s for s in self._sessions.values() if s["user_id"] == user_id]

    def get_audit_log(self, org_id: Optional[str] = None, limit: int = 100) -> list[dict]:
        log = self._audit_log
        if org_id:
            log = [l for l in log if l.get("org_id") == org_id]
        return log[-limit:]

    def get_stats(self, org_id: Optional[str] = None) -> dict:
        sessions = list(self._sessions.values())
        if org_id:
            sessions = [s for s in sessions if s["organization_id"] == org_id]
        return {"total_sessions": len(sessions), "active": sum(1 for s in sessions if s["is_active"]), "expired": sum(1 for s in sessions if not s["is_active"])}


break_glass_service = BreakGlassService()
