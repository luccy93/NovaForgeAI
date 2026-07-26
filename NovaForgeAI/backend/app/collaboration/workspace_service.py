"""Workspace Service — personal, team, department, org, project, repo, temporary, shared workspaces."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class WorkspaceScope(Enum):
    PERSONAL = "personal"
    TEAM = "team"
    DEPARTMENT = "department"
    ORGANIZATION = "organization"
    PROJECT = "project"
    REPOSITORY = "repository"
    TEMPORARY = "temporary"
    SHARED = "shared"


class WorkspaceVisibility(Enum):
    PRIVATE = "private"
    TEAM = "team"
    ORGANIZATION = "organization"
    PUBLIC = "public"


@dataclass
class Workspace:
    id: str
    org_id: str
    name: str
    scope: WorkspaceScope
    visibility: WorkspaceVisibility = WorkspaceVisibility.TEAM
    description: str = ""
    owner_id: str = ""
    members: list = field(default_factory=list)
    settings: dict = field(default_factory=dict)
    tags: list = field(default_factory=list)
    is_active: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["scope"] = self.scope.value
        d["visibility"] = self.visibility.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Workspace":
        data = data.copy()
        data["scope"] = WorkspaceScope(data.get("scope", "team"))
        data["visibility"] = WorkspaceVisibility(data.get("visibility", "team"))
        return cls(**data)


class WorkspaceService:
    def __init__(self, storage_dir: str = "collab_data/workspaces"):
        self.storage_dir = storage_dir
        self._workspaces: dict[str, Workspace] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _store_path(self) -> str: return os.path.join(self.storage_dir, "workspaces.json")

    def _load(self) -> None:
        path = self._store_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    try: self._workspaces[k] = Workspace.from_dict(v)
                    except Exception as e: logger.warning("Skipping workspace %s: %s", k, e)
            except Exception as e: logger.error("Failed to load workspaces: %s", e)

    def _save(self) -> None:
        try:
            with open(self._store_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._workspaces.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save workspaces: %s", e)

    def create(self, name: str, org_id: str, scope: WorkspaceScope, owner_id: str = "", description: str = "", visibility: WorkspaceVisibility = WorkspaceVisibility.TEAM) -> Workspace:
        ws = Workspace(id=str(uuid.uuid4()), org_id=org_id, name=name, scope=scope, owner_id=owner_id, description=description, visibility=visibility)
        ws.members.append({"user_id": owner_id, "role": "owner", "joined_at": datetime.now(timezone.utc).isoformat()})
        self._workspaces[ws.id] = ws
        self._save()
        return ws

    def get(self, ws_id: str) -> Optional[Workspace]: return self._workspaces.get(ws_id)

    def update(self, ws_id: str, updates: dict) -> Optional[Workspace]:
        ws = self._workspaces.get(ws_id)
        if not ws: return None
        for k, v in updates.items():
            if hasattr(ws, k) and k not in ("id", "created_at"):
                if k == "scope": setattr(ws, k, WorkspaceScope(v) if isinstance(v, str) else v)
                elif k == "visibility": setattr(ws, k, WorkspaceVisibility(v) if isinstance(v, str) else v)
                else: setattr(ws, k, v)
        ws.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return ws

    def add_member(self, ws_id: str, user_id: str, role: str = "member") -> bool:
        ws = self._workspaces.get(ws_id)
        if not ws: return False
        if not any(m["user_id"] == user_id for m in ws.members):
            ws.members.append({"user_id": user_id, "role": role, "joined_at": datetime.now(timezone.utc).isoformat()})
            ws.updated_at = datetime.now(timezone.utc).isoformat()
            self._save()
        return True

    def remove_member(self, ws_id: str, user_id: str) -> bool:
        ws = self._workspaces.get(ws_id)
        if not ws: return False
        ws.members = [m for m in ws.members if m["user_id"] != user_id]
        ws.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return True

    def list_by_org(self, org_id: str, scope: Optional[WorkspaceScope] = None) -> list[Workspace]:
        results = [ws for ws in self._workspaces.values() if ws.org_id == org_id and ws.is_active]
        if scope: results = [ws for ws in results if ws.scope == scope]
        return results

    def list_by_user(self, user_id: str) -> list[Workspace]:
        return [ws for ws in self._workspaces.values() if ws.is_active and any(m["user_id"] == user_id for m in ws.members)]

    def get_telemetry(self) -> dict: return dict(self._telemetry)
