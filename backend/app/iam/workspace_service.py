"""Workspace service — workspace CRUD within organizations."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional


class WorkspaceService:
    def __init__(self):
        self._workspaces: dict[str, dict] = {}

    def create(self, org_id: str, name: str, slug: str, created_by: str = "", description: str = "", settings: Optional[dict] = None) -> dict:
        ws_id = str(uuid.uuid4())
        ws = {"id": ws_id, "organization_id": org_id, "name": name, "slug": slug, "description": description, "settings": settings or {}, "is_active": True, "project_count": 0, "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat(), "created_by": created_by}
        self._workspaces[ws_id] = ws
        return ws

    def get(self, workspace_id: str) -> Optional[dict]:
        return self._workspaces.get(workspace_id)

    def get_by_slug(self, org_id: str, slug: str) -> Optional[dict]:
        for ws in self._workspaces.values():
            if ws["organization_id"] == org_id and ws["slug"] == slug:
                return ws
        return None

    def list_for_org(self, org_id: str) -> list[dict]:
        return [ws for ws in self._workspaces.values() if ws["organization_id"] == org_id]

    def list_active(self, org_id: str) -> list[dict]:
        return [ws for ws in self._workspaces.values() if ws["organization_id"] == org_id and ws["is_active"]]

    def update(self, workspace_id: str, updates: dict) -> Optional[dict]:
        ws = self._workspaces.get(workspace_id)
        if not ws:
            return None
        for key in ("name", "description", "settings", "is_active"):
            if key in updates:
                ws[key] = updates[key]
        ws["updated_at"] = datetime.now(timezone.utc).isoformat()
        return ws

    def delete(self, workspace_id: str) -> bool:
        return self._workspaces.pop(workspace_id, None) is not None

    def deactivate(self, workspace_id: str) -> bool:
        ws = self._workspaces.get(workspace_id)
        if not ws:
            return False
        ws["is_active"] = False
        ws["updated_at"] = datetime.now(timezone.utc).isoformat()
        return True

    def get_stats(self, org_id: str) -> dict:
        ws_list = self.list_for_org(org_id)
        return {"total": len(ws_list), "active": sum(1 for w in ws_list if w["is_active"]), "total_projects": sum(w.get("project_count", 0) for w in ws_list)}


workspace_service = WorkspaceService()
