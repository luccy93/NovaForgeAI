"""Organization service — CRUD and lifecycle management for organizations."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional


class OrganizationService:
    def __init__(self):
        self._organizations: dict[str, dict] = {}
        self._suspended_orgs: set[str] = set()

    def create(self, name: str, slug: str, owner_id: str, description: str = "", plan: str = "free", settings: Optional[dict] = None) -> dict:
        org_id = str(uuid.uuid4())
        org = {"id": org_id, "name": name, "slug": slug, "description": description, "plan": plan, "settings": settings or {}, "is_active": True, "state": "ACTIVE", "owner_id": owner_id, "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat(), "member_count": 1, "team_count": 0, "workspace_count": 0, "project_count": 0}
        self._organizations[org_id] = org
        return org

    def get(self, org_id: str) -> Optional[dict]:
        return self._organizations.get(org_id)

    def get_by_slug(self, slug: str) -> Optional[dict]:
        for org in self._organizations.values():
            if org["slug"] == slug:
                return org
        return None

    def update(self, org_id: str, updates: dict) -> Optional[dict]:
        org = self._organizations.get(org_id)
        if not org:
            return None
        for key in ("name", "description", "plan", "settings", "is_active"):
            if key in updates:
                org[key] = updates[key]
        org["updated_at"] = datetime.now(timezone.utc).isoformat()
        return org

    def delete(self, org_id: str) -> bool:
        if org_id in self._organizations:
            self._organizations[org_id]["state"] = "DELETED"
            self._organizations[org_id]["is_active"] = False
            return True
        return False

    def suspend(self, org_id: str, reason: str = "") -> bool:
        org = self._organizations.get(org_id)
        if not org:
            return False
        org["state"] = "SUSPENDED"
        org["is_active"] = False
        org["suspension_reason"] = reason
        org["suspended_at"] = datetime.now(timezone.utc).isoformat()
        self._suspended_orgs.add(org_id)
        return True

    def reactivate(self, org_id: str) -> bool:
        org = self._organizations.get(org_id)
        if not org:
            return False
        org["state"] = "ACTIVE"
        org["is_active"] = True
        org.pop("suspension_reason", None)
        org.pop("suspended_at", None)
        self._suspended_orgs.discard(org_id)
        return True

    def list_all(self, state: Optional[str] = None) -> list[dict]:
        orgs = list(self._organizations.values())
        if state:
            orgs = [o for o in orgs if o["state"] == state]
        return orgs

    def list_active(self) -> list[dict]:
        return [o for o in self._organizations.values() if o["is_active"]]

    def get_stats(self, org_id: str) -> dict:
        org = self._organizations.get(org_id)
        if not org:
            return {"error": "Organization not found"}
        return {"org_id": org_id, "name": org["name"], "state": org["state"], "member_count": org.get("member_count", 0), "team_count": org.get("team_count", 0), "workspace_count": org.get("workspace_count", 0), "project_count": org.get("project_count", 0), "plan": org["plan"]}

    def verify_domain(self, org_id: str, domain: str) -> dict:
        token = str(uuid.uuid4())[:16]
        verification = {"domain": domain, "organization_id": org_id, "verification_token": token, "method": "dns", "is_verified": False, "created_at": datetime.now(timezone.utc).isoformat()}
        return verification

    def check_state(self, org_id: str) -> str:
        org = self._organizations.get(org_id)
        if not org:
            return "not_found"
        return org["state"]


org_service = OrganizationService()
