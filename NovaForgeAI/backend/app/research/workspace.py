"""Research Workspace — sandboxed environments for AI experiments."""
import json, uuid, os, logging, shutil
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class WorkspaceStatus(Enum):
    CREATING = "creating"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    DELETED = "deleted"


class WorkspaceType(Enum):
    EXPERIMENT = "experiment"
    EVALUATION = "evaluation"
    BENCHMARK = "benchmark"
    TRAINING = "training"
    ANALYSIS = "analysis"
    PROTOTYPE = "prototype"


@dataclass
class WorkspaceFile:
    path: str
    content_type: str = "text/plain"
    size: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)


@dataclass
class Workspace:
    id: str
    org_id: str
    name: str
    description: str = ""
    workspace_type: WorkspaceType = WorkspaceType.EXPERIMENT
    status: WorkspaceStatus = WorkspaceStatus.CREATING
    files: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    tags: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["workspace_type"] = self.workspace_type.value
        d["status"] = self.status.value
        d["files"] = {k: v.to_dict() for k, v in self.files.items()}
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Workspace":
        data = data.copy()
        data["workspace_type"] = WorkspaceType(data.get("workspace_type", "experiment"))
        data["status"] = WorkspaceStatus(data.get("status", "creating"))
        files_data = data.pop("files", {})
        w = cls(**data)
        w.files = {k: WorkspaceFile(**v) if isinstance(v, dict) else v for k, v in files_data.items()}
        return w


class ResearchWorkspace:
    def __init__(self, storage_dir: str = "research_data/workspaces"):
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

    def create_workspace(self, name: str, org_id: str, ws_type: WorkspaceType = WorkspaceType.EXPERIMENT, description: str = "") -> Workspace:
        ws = Workspace(id=str(uuid.uuid4()), org_id=org_id, name=name, description=description, workspace_type=ws_type, status=WorkspaceStatus.ACTIVE)
        self._workspaces[ws.id] = ws
        self._save()
        return ws

    def get_workspace(self, ws_id: str) -> Optional[Workspace]: return self._workspaces.get(ws_id)

    def update_workspace(self, ws_id: str, updates: dict) -> Optional[Workspace]:
        ws = self._workspaces.get(ws_id)
        if not ws: return None
        for k, v in updates.items():
            if hasattr(ws, k) and k not in ("id", "created_at"):
                if k == "workspace_type": setattr(ws, k, WorkspaceType(v) if isinstance(v, str) else v)
                elif k == "status": setattr(ws, k, WorkspaceStatus(v) if isinstance(v, str) else v)
                else: setattr(ws, k, v)
        ws.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return ws

    def list_workspaces(self, org_id: str = "", ws_type: Optional[WorkspaceType] = None) -> list[Workspace]:
        results = []
        for ws in self._workspaces.values():
            if org_id and ws.org_id != org_id: continue
            if ws_type and ws.workspace_type != ws_type: continue
            results.append(ws)
        return results

    def add_file(self, ws_id: str, file_path: str, content: str, content_type: str = "text/plain") -> Optional[WorkspaceFile]:
        ws = self._workspaces.get(ws_id)
        if not ws: return None
        wf = WorkspaceFile(path=file_path, content_type=content_type, size=len(content.encode("utf-8")))
        ws.files[file_path] = wf
        full_path = os.path.join(self.storage_dir, ws_id, file_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f: f.write(content)
        ws.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return wf

    def read_file(self, ws_id: str, file_path: str) -> Optional[str]:
        ws = self._workspaces.get(ws_id)
        if not ws or file_path not in ws.files: return None
        full_path = os.path.join(self.storage_dir, ws_id, file_path)
        if os.path.exists(full_path):
            with open(full_path, "r", encoding="utf-8") as f: return f.read()
        return None

    def delete_workspace(self, ws_id: str) -> bool:
        if ws_id not in self._workspaces: return False
        ws_dir = os.path.join(self.storage_dir, ws_id)
        if os.path.exists(ws_dir): shutil.rmtree(ws_dir)
        del self._workspaces[ws_id]
        self._save()
        return True

    def clone_workspace(self, ws_id: str, new_name: str) -> Optional[Workspace]:
        original = self._workspaces.get(ws_id)
        if not original: return None
        clone = Workspace(
            id=str(uuid.uuid4()), org_id=original.org_id, name=new_name,
            description=f"Clone of {original.name}", workspace_type=original.workspace_type,
            status=WorkspaceStatus.CREATING, tags=original.tags.copy(), metadata=original.metadata.copy(),
        )
        self._workspaces[clone.id] = clone
        self._save()
        return clone

    def get_telemetry(self) -> dict: return dict(self._telemetry)
