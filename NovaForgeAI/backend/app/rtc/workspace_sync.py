"""Workspace Sync — real-time state sync, snapshots, history, restore, templates."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional, Any

logger = logging.getLogger(__name__)

@dataclass
class Workspace:
    id: str; org_id: str; name: str; ws_type: str = "team"  # personal, team, org, repo, temp, shared, guest, cross_org
    owner_id: str = ""; members: list = field(default_factory=list)
    state: dict = field(default_factory=dict); snapshots: list = field(default_factory=list)
    template_id: str = ""; is_active: bool = True; tags: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "Workspace": return cls(**data)

@dataclass
class WorkspaceSnapshot:
    id: str; workspace_id: str; state: dict; version: int = 1
    created_by: str = ""; label: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "WorkspaceSnapshot": return cls(**data)

class WorkspaceSync:
    def __init__(self, storage_dir: str = "rtc_data/workspaces"):
        self.storage_dir = storage_dir; self._workspaces: dict[str, Workspace] = {}
        self._snapshots: dict[str, WorkspaceSnapshot] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _ws_path(self) -> str: return os.path.join(self.storage_dir, "workspaces.json")
    def _snap_path(self) -> str: return os.path.join(self.storage_dir, "snapshots.json")

    def _load(self) -> None:
        for path, store, cls in [(self._ws_path(), self._workspaces, Workspace), (self._snap_path(), self._snapshots, WorkspaceSnapshot)]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f: data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = cls.from_dict(v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._ws_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._workspaces.items()}, f, indent=2, default=str)
            with open(self._snap_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._snapshots.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def create(self, org_id: str, name: str, ws_type: str = "team", owner_id: str = "") -> Workspace:
        ws = Workspace(id=str(uuid.uuid4()), org_id=org_id, name=name, ws_type=ws_type, owner_id=owner_id)
        self._workspaces[ws.id] = ws; self._save(); return ws

    def get(self, ws_id: str) -> Optional[Workspace]: return self._workspaces.get(ws_id)

    def update_state(self, ws_id: str, state: dict) -> Optional[Workspace]:
        ws = self._workspaces.get(ws_id)
        if not ws: return None
        ws.state.update(state); ws.updated_at = datetime.now(timezone.utc).isoformat(); self._save(); return ws

    def snapshot(self, ws_id: str, created_by: str = "", label: str = "") -> Optional[WorkspaceSnapshot]:
        ws = self._workspaces.get(ws_id)
        if not ws: return None
        version = len([s for s in self._snapshots.values() if s.workspace_id == ws_id]) + 1
        snap = WorkspaceSnapshot(id=str(uuid.uuid4()), workspace_id=ws_id, state=ws.state.copy(), version=version, created_by=created_by, label=label)
        self._snapshots[snap.id] = snap; ws.snapshots.append(snap.id); self._save(); return snap

    def restore(self, ws_id: str, snapshot_id: str) -> Optional[Workspace]:
        ws = self._workspaces.get(ws_id); snap = self._snapshots.get(snapshot_id)
        if not ws or not snap: return None
        ws.state = snap.state.copy(); ws.updated_at = datetime.now(timezone.utc).isoformat(); self._save(); return ws

    def add_member(self, ws_id: str, user_id: str) -> bool:
        ws = self._workspaces.get(ws_id)
        if not ws: return False
        if user_id not in ws.members: ws.members.append(user_id); self._save()
        return True

    def get_telemetry(self) -> dict: return {"workspaces": len(self._workspaces), "snapshots": len(self._snapshots)}
