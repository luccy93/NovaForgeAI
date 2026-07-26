"""Team Service — teams, sub-teams, departments, engineering groups, invitations, ownership, permissions, workspace membership."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class TeamType(Enum):
    TEAM = "team"
    SUB_TEAM = "sub_team"
    DEPARTMENT = "department"
    ENGINEERING_GROUP = "engineering_group"


@dataclass
class Team:
    id: str
    org_id: str
    name: str
    team_type: TeamType = TeamType.TEAM
    description: str = ""
    parent_id: str = ""
    owner_id: str = ""
    members: list = field(default_factory=list)
    permissions: dict = field(default_factory=dict)
    settings: dict = field(default_factory=dict)
    tags: list = field(default_factory=list)
    is_active: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["team_type"] = self.team_type.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Team":
        data = data.copy()
        data["team_type"] = TeamType(data.get("team_type", "team"))
        return cls(**data)


@dataclass
class Invitation:
    id: str
    team_id: str
    inviter_id: str
    invitee_email: str = ""
    role: str = "member"
    status: str = "pending"
    expires_at: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "Invitation": return cls(**data)


class TeamService:
    def __init__(self, storage_dir: str = "collab_data/teams"):
        self.storage_dir = storage_dir
        self._teams: dict[str, Team] = {}
        self._invitations: dict[str, Invitation] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _teams_path(self) -> str: return os.path.join(self.storage_dir, "teams.json")
    def _invites_path(self) -> str: return os.path.join(self.storage_dir, "invitations.json")

    def _load(self) -> None:
        for path, store, cls in [
            (self._teams_path(), self._teams, Team),
            (self._invites_path(), self._invitations, Invitation),
        ]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = cls.from_dict(v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Failed to load team data: %s", e)

    def _save(self) -> None:
        try:
            with open(self._teams_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._teams.items()}, f, indent=2, default=str)
            with open(self._invites_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._invitations.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save team data: %s", e)

    def create_team(self, name: str, org_id: str, team_type: TeamType = TeamType.TEAM, owner_id: str = "", parent_id: str = "") -> Team:
        team = Team(id=str(uuid.uuid4()), org_id=org_id, name=name, team_type=team_type, owner_id=owner_id, parent_id=parent_id)
        if owner_id:
            team.members.append({"user_id": owner_id, "role": "owner", "joined_at": datetime.now(timezone.utc).isoformat()})
        self._teams[team.id] = team
        self._save()
        return team

    def get_team(self, team_id: str) -> Optional[Team]: return self._teams.get(team_id)

    def update_team(self, team_id: str, updates: dict) -> Optional[Team]:
        team = self._teams.get(team_id)
        if not team: return None
        for k, v in updates.items():
            if hasattr(team, k) and k not in ("id", "created_at"):
                if k == "team_type": setattr(team, k, TeamType(v) if isinstance(v, str) else v)
                else: setattr(team, k, v)
        team.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return team

    def add_member(self, team_id: str, user_id: str, role: str = "member") -> bool:
        team = self._teams.get(team_id)
        if not team: return False
        if not any(m["user_id"] == user_id for m in team.members):
            team.members.append({"user_id": user_id, "role": role, "joined_at": datetime.now(timezone.utc).isoformat()})
            team.updated_at = datetime.now(timezone.utc).isoformat()
            self._save()
        return True

    def remove_member(self, team_id: str, user_id: str) -> bool:
        team = self._teams.get(team_id)
        if not team: return False
        team.members = [m for m in team.members if m["user_id"] != user_id]
        team.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return True

    def invite(self, team_id: str, inviter_id: str, invitee_email: str, role: str = "member") -> Optional[Invitation]:
        inv = Invitation(id=str(uuid.uuid4()), team_id=team_id, inviter_id=inviter_id, invitee_email=invitee_email, role=role, expires_at=(datetime.now(timezone.utc).isoformat()))
        self._invitations[inv.id] = inv
        self._save()
        return inv

    def accept_invitation(self, inv_id: str) -> bool:
        inv = self._invitations.get(inv_id)
        if not inv or inv.status != "pending": return False
        inv.status = "accepted"
        self._save()
        return True

    def list_teams(self, org_id: str = "", team_type: Optional[TeamType] = None) -> list[Team]:
        results = [t for t in self._teams.values() if t.is_active]
        if org_id: results = [t for t in results if t.org_id == org_id]
        if team_type: results = [t for t in results if t.team_type == team_type]
        return results

    def get_sub_teams(self, parent_id: str) -> list[Team]:
        return [t for t in self._teams.values() if t.parent_id == parent_id and t.is_active]

    def list_invitations(self, team_id: str = "") -> list[Invitation]:
        results = list(self._invitations.values())
        if team_id: results = [i for i in results if i.team_id == team_id]
        return results

    def get_telemetry(self) -> dict: return dict(self._telemetry)
