"""Developer Workspace — templates, cloning, export, import, snapshot, restore for personal and team workspaces."""
import json, uuid, os, logging, shutil
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class WorkspaceTemplateType(Enum):
    PROJECT = "project"
    LANGUAGE = "language"
    FRAMEWORK = "framework"
    ORGANIZATION = "organization"
    EMPTY = "empty"


@dataclass
class DeveloperWorkspace:
    id: str
    user_id: str
    org_id: str
    name: str
    description: str = ""
    template_type: WorkspaceTemplateType = WorkspaceTemplateType.EMPTY
    template_id: str = ""
    settings: dict = field(default_factory=dict)
    is_active: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["template_type"] = self.template_type.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "DeveloperWorkspace":
        data = data.copy()
        data["template_type"] = WorkspaceTemplateType(data.get("template_type", "empty"))
        return cls(**data)


@dataclass
class WorkspaceSnapshot:
    id: str
    workspace_id: str
    version: int
    data: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "WorkspaceSnapshot": return cls(**data)


class DeveloperWorkspaceService:
    def __init__(self, storage_dir: str = "dx_data/workspaces"):
        self.storage_dir = storage_dir
        self._workspaces: dict[str, DeveloperWorkspace] = {}
        self._snapshots: dict[str, WorkspaceSnapshot] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _ws_path(self) -> str: return os.path.join(self.storage_dir, "workspaces.json")
    def _snap_path(self) -> str: return os.path.join(self.storage_dir, "snapshots.json")

    def _load(self) -> None:
        for path, store, cls in [
            (self._ws_path(), self._workspaces, DeveloperWorkspace),
            (self._snap_path(), self._snapshots, WorkspaceSnapshot),
        ]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = cls.from_dict(v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Failed to load DX workspaces: %s", e)

    def _save(self) -> None:
        try:
            with open(self._ws_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._workspaces.items()}, f, indent=2, default=str)
            with open(self._snap_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._snapshots.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save DX workspaces: %s", e)

    def create(self, user_id: str, org_id: str, name: str, template_type: WorkspaceTemplateType = WorkspaceTemplateType.EMPTY, template_id: str = "", description: str = "") -> DeveloperWorkspace:
        ws = DeveloperWorkspace(id=str(uuid.uuid4()), user_id=user_id, org_id=org_id, name=name, description=description, template_type=template_type, template_id=template_id)
        self._workspaces[ws.id] = ws
        self._save()
        return ws

    def get(self, ws_id: str) -> Optional[DeveloperWorkspace]: return self._workspaces.get(ws_id)

    def update(self, ws_id: str, updates: dict) -> Optional[DeveloperWorkspace]:
        ws = self._workspaces.get(ws_id)
        if not ws: return None
        for k, v in updates.items():
            if hasattr(ws, k) and k not in ("id", "created_at"): setattr(ws, k, v)
        ws.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return ws

    def clone(self, ws_id: str, new_name: str) -> Optional[DeveloperWorkspace]:
        original = self._workspaces.get(ws_id)
        if not original: return None
        clone = DeveloperWorkspace(id=str(uuid.uuid4()), user_id=original.user_id, org_id=original.org_id, name=new_name, description=f"Clone of {original.name}", template_type=original.template_type, settings=original.settings.copy())
        self._workspaces[clone.id] = clone
        self._save()
        return clone

    def create_snapshot(self, workspace_id: str) -> Optional[WorkspaceSnapshot]:
        ws = self._workspaces.get(workspace_id)
        if not ws: return None
        existing = [s for s in self._snapshots.values() if s.workspace_id == workspace_id]
        version = max((s.version for s in existing), default=0) + 1
        snap = WorkspaceSnapshot(id=str(uuid.uuid4()), workspace_id=workspace_id, version=version, data=ws.to_dict())
        self._snapshots[snap.id] = snap
        self._save()
        return snap

    def restore(self, workspace_id: str, version: int = -1) -> Optional[DeveloperWorkspace]:
        snaps = [s for s in self._snapshots.values() if s.workspace_id == workspace_id]
        if not snaps: return None
        snaps.sort(key=lambda s: s.version)
        target = snaps[-1] if version == -1 else next((s for s in snaps if s.version == version), None)
        if not target: return None
        return DeveloperWorkspace.from_dict(target.data)

    def export(self, ws_id: str) -> Optional[dict]:
        ws = self._workspaces.get(ws_id)
        return ws.to_dict() if ws else None

    def import_workspace(self, data: dict) -> DeveloperWorkspace:
        ws = DeveloperWorkspace.from_dict(data)
        ws.id = str(uuid.uuid4())
        self._workspaces[ws.id] = ws
        self._save()
        return ws

    def list_by_user(self, user_id: str) -> list[DeveloperWorkspace]:
        return [ws for ws in self._workspaces.values() if ws.user_id == user_id and ws.is_active]

    def get_telemetry(self) -> dict: return dict(self._telemetry)
