"""Team service — team CRUD and member management."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional


class TeamService:
    def __init__(self):
        self._teams: dict[str, dict] = {}
        self._team_members: dict[str, dict[str, str]] = {}

    def create(self, org_id: str, name: str, description: str = "", parent_team_id: Optional[str] = None) -> dict:
        team_id = str(uuid.uuid4())
        team = {"id": team_id, "organization_id": org_id, "name": name, "description": description, "parent_team_id": parent_team_id, "is_active": True, "member_count": 0, "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat()}
        self._teams[team_id] = team
        self._team_members[team_id] = {}
        return team

    def get(self, team_id: str) -> Optional[dict]:
        return self._teams.get(team_id)

    def list_for_org(self, org_id: str) -> list[dict]:
        return [t for t in self._teams.values() if t["organization_id"] == org_id]

    def update(self, team_id: str, updates: dict) -> Optional[dict]:
        team = self._teams.get(team_id)
        if not team:
            return None
        for key in ("name", "description", "parent_team_id"):
            if key in updates:
                team[key] = updates[key]
        team["updated_at"] = datetime.now(timezone.utc).isoformat()
        return team

    def delete(self, team_id: str) -> bool:
        self._team_members.pop(team_id, None)
        return self._teams.pop(team_id, None) is not None

    def add_member(self, team_id: str, user_id: str, role: str = "member") -> dict:
        members = self._team_members.setdefault(team_id, {})
        members[user_id] = role
        team = self._teams.get(team_id)
        if team:
            team["member_count"] = len(members)
        return {"team_id": team_id, "user_id": user_id, "role": role, "added_at": datetime.now(timezone.utc).isoformat()}

    def remove_member(self, team_id: str, user_id: str) -> bool:
        members = self._team_members.get(team_id, {})
        if user_id in members:
            del members[user_id]
            team = self._teams.get(team_id)
            if team:
                team["member_count"] = len(members)
            return True
        return False

    def list_members(self, team_id: str) -> list[dict]:
        members = self._team_members.get(team_id, {})
        return [{"user_id": uid, "role": role} for uid, role in members.items()]

    def get_user_teams(self, org_id: str, user_id: str) -> list[dict]:
        return [t for t in self._teams.values() if t["organization_id"] == org_id and user_id in self._team_members.get(t["id"], {})]

    def get_child_teams(self, team_id: str) -> list[dict]:
        return [t for t in self._teams.values() if t.get("parent_team_id") == team_id]

    def get_stats(self, org_id: str) -> dict:
        teams = self.list_for_org(org_id)
        return {"total_teams": len(teams), "active": sum(1 for t in teams if t["is_active"]), "total_memberships": sum(t.get("member_count", 0) for t in teams)}


team_service = TeamService()
