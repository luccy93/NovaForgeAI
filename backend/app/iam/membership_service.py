"""Membership service — invite, accept, remove, suspend, role assignment."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional
from app.iam.constants import IAMRole


class MembershipService:
    def __init__(self):
        self._memberships: dict[str, dict] = {}
        self._invitations: dict[str, dict] = {}

    def invite(self, org_id: str, email: str, role: str = "viewer", invited_by: str = "", team_ids: Optional[list[str]] = None, message: str = "") -> dict:
        invite_id = str(uuid.uuid4())
        invitation = {"id": invite_id, "organization_id": org_id, "email": email, "role": role, "invited_by": invited_by, "team_ids": team_ids or [], "message": message, "status": "pending", "created_at": datetime.now(timezone.utc).isoformat(), "expires_at": datetime.now(timezone.utc).isoformat()}
        self._invitations[invite_id] = invitation
        return invitation

    def accept_invitation(self, invitation_id: str, user_id: str) -> dict:
        inv = self._invitations.get(invitation_id)
        if not inv or inv["status"] != "pending":
            return {"error": "Invalid or expired invitation"}
        inv["status"] = "accepted"
        inv["accepted_at"] = datetime.now(timezone.utc).isoformat()
        membership = self.add_member(inv["organization_id"], user_id, inv["role"], invited_by=inv["invited_by"])
        membership["invitation_id"] = invitation_id
        return membership

    def add_member(self, org_id: str, user_id: str, role: str = "viewer", invited_by: str = "") -> dict:
        existing = self.get_membership(org_id, user_id)
        if existing:
            return existing
        mem_id = str(uuid.uuid4())
        mem = {"id": mem_id, "user_id": user_id, "organization_id": org_id, "role": role, "is_active": True, "invited_by": invited_by, "joined_at": datetime.now(timezone.utc).isoformat(), "created_at": datetime.now(timezone.utc).isoformat()}
        self._memberships[mem_id] = mem
        return mem

    def get_membership(self, org_id: str, user_id: str) -> Optional[dict]:
        for mem in self._memberships.values():
            if mem["organization_id"] == org_id and mem["user_id"] == user_id:
                return mem
        return None

    def get_membership_by_id(self, membership_id: str) -> Optional[dict]:
        return self._memberships.get(membership_id)

    def list_members(self, org_id: str, active_only: bool = True) -> list[dict]:
        members = [m for m in self._memberships.values() if m["organization_id"] == org_id]
        if active_only:
            members = [m for m in members if m["is_active"]]
        return members

    def list_pending_invitations(self, org_id: str) -> list[dict]:
        return [i for i in self._invitations.values() if i["organization_id"] == org_id and i["status"] == "pending"]

    def update_role(self, org_id: str, user_id: str, new_role: str, reason: str = "") -> Optional[dict]:
        mem = self.get_membership(org_id, user_id)
        if not mem:
            return None
        old_role = mem["role"]
        mem["role"] = new_role
        mem["role_changed_at"] = datetime.now(timezone.utc).isoformat()
        mem["role_change_reason"] = reason
        return mem

    def remove_member(self, org_id: str, user_id: str, reason: str = "", transfer_to: str = "") -> bool:
        mem = self.get_membership(org_id, user_id)
        if not mem:
            return False
        mem["is_active"] = False
        mem["removed_at"] = datetime.now(timezone.utc).isoformat()
        mem["removal_reason"] = reason
        if transfer_to:
            mem["transferred_to"] = transfer_to
        return True

    def suspend_member(self, org_id: str, user_id: str, reason: str = "") -> bool:
        mem = self.get_membership(org_id, user_id)
        if not mem:
            return False
        mem["is_active"] = False
        mem["suspended_at"] = datetime.now(timezone.utc).isoformat()
        mem["suspension_reason"] = reason
        return True

    def reactivate_member(self, org_id: str, user_id: str) -> bool:
        mem = self.get_membership(org_id, user_id)
        if not mem:
            return False
        mem["is_active"] = True
        mem.pop("suspended_at", None)
        mem.pop("suspension_reason", None)
        return True

    def is_member(self, org_id: str, user_id: str) -> bool:
        mem = self.get_membership(org_id, user_id)
        return mem is not None and mem["is_active"]

    def get_user_organizations(self, user_id: str) -> list[dict]:
        return [m for m in self._memberships.values() if m["user_id"] == user_id and m["is_active"]]

    def get_user_role(self, org_id: str, user_id: str) -> Optional[str]:
        mem = self.get_membership(org_id, user_id)
        return mem["role"] if mem and mem["is_active"] else None

    def get_stats(self, org_id: str) -> dict:
        members = [m for m in self._memberships.values() if m["organization_id"] == org_id]
        role_counts = {}
        for m in members:
            if m["is_active"]:
                role_counts[m["role"]] = role_counts.get(m["role"], 0) + 1
        return {"total_members": len(members), "active": sum(1 for m in members if m["is_active"]), "by_role": role_counts, "pending_invitations": len(self.list_pending_invitations(org_id))}


membership_service = MembershipService()
