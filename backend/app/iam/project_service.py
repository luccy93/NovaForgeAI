"""Project service — project CRUD within workspaces."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional


class ProjectService:
    def __init__(self):
        self._projects: dict[str, dict] = {}

    def create(self, org_id: str, workspace_id: str, name: str, slug: str, created_by: str = "", description: str = "", settings: Optional[dict] = None) -> dict:
        proj_id = str(uuid.uuid4())
        proj = {"id": proj_id, "organization_id": org_id, "workspace_id": workspace_id, "name": name, "slug": slug, "description": description, "settings": settings or {}, "is_active": True, "is_archived": False, "repository_count": 0, "service_count": 0, "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat(), "created_by": created_by}
        self._projects[proj_id] = proj
        return proj

    def get(self, project_id: str) -> Optional[dict]:
        return self._projects.get(project_id)

    def get_by_slug(self, workspace_id: str, slug: str) -> Optional[dict]:
        for p in self._projects.values():
            if p["workspace_id"] == workspace_id and p["slug"] == slug:
                return p
        return None

    def list_for_workspace(self, workspace_id: str) -> list[dict]:
        return [p for p in self._projects.values() if p["workspace_id"] == workspace_id]

    def list_for_org(self, org_id: str) -> list[dict]:
        return [p for p in self._projects.values() if p["organization_id"] == org_id]

    def update(self, project_id: str, updates: dict) -> Optional[dict]:
        proj = self._projects.get(project_id)
        if not proj:
            return None
        for key in ("name", "description", "settings", "is_active", "is_archived"):
            if key in updates:
                proj[key] = updates[key]
        proj["updated_at"] = datetime.now(timezone.utc).isoformat()
        return proj

    def delete(self, project_id: str) -> bool:
        return self._projects.pop(project_id, None) is not None

    def archive(self, project_id: str) -> bool:
        proj = self._projects.get(project_id)
        if not proj:
            return False
        proj["is_archived"] = True
        proj["updated_at"] = datetime.now(timezone.utc).isoformat()
        return True

    def get_stats(self, org_id: str) -> dict:
        projs = self.list_for_org(org_id)
        return {"total": len(projs), "active": sum(1 for p in projs if p["is_active"]), "archived": sum(1 for p in projs if p.get("is_archived"))}


project_service = ProjectService()
