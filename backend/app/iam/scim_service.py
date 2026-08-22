"""SCIM service — enterprise provisioning (create/update/deactivate users, group sync)."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional


class SCIMService:
    def __init__(self):
        self._directories: dict[str, dict] = {}
        self._scim_users: dict[str, dict] = {}
        self._scim_groups: dict[str, dict] = {}
        self._sync_jobs: list[dict] = []

    def create_directory(self, org_id: str, name: str, provider: str, config: Optional[dict] = None) -> dict:
        dir_id = str(uuid.uuid4())
        directory = {"id": dir_id, "organization_id": org_id, "name": name, "provider": provider, "config": config or {}, "is_active": True, "last_sync_at": None, "sync_status": "idle", "created_at": datetime.now(timezone.utc).isoformat()}
        self._directories[dir_id] = directory
        return directory

    def get_directory(self, dir_id: str) -> Optional[dict]:
        return self._directories.get(dir_id)

    def list_directories(self, org_id: str) -> list[dict]:
        return [d for d in self._directories.values() if d["organization_id"] == org_id]

    def provision_user(self, dir_id: str, external_id: str, email: str, display_name: str = "", groups: Optional[list[str]] = None, attributes: Optional[dict] = None) -> dict:
        user_id = str(uuid.uuid4())
        user = {"id": user_id, "directory_id": dir_id, "external_id": external_id, "email": email, "display_name": display_name, "groups": groups or [], "attributes": attributes or {}, "is_active": True, "provisioned_at": datetime.now(timezone.utc).isoformat(), "last_synced_at": datetime.now(timezone.utc).isoformat()}
        self._scim_users[user_id] = user
        return user

    def update_user(self, user_id: str, updates: dict) -> Optional[dict]:
        user = self._scim_users.get(user_id)
        if not user:
            return None
        for key in ("email", "display_name", "groups", "attributes", "is_active"):
            if key in updates:
                user[key] = updates[key]
        user["last_synced_at"] = datetime.now(timezone.utc).isoformat()
        return user

    def deactivate_user(self, user_id: str) -> bool:
        user = self._scim_users.get(user_id)
        if not user:
            return False
        user["is_active"] = False
        user["deactivated_at"] = datetime.now(timezone.utc).isoformat()
        user["last_synced_at"] = datetime.now(timezone.utc).isoformat()
        return True

    def get_user(self, user_id: str) -> Optional[dict]:
        return self._scim_users.get(user_id)

    def list_users(self, dir_id: Optional[str] = None, active_only: bool = True) -> list[dict]:
        users = list(self._scim_users.values())
        if dir_id:
            users = [u for u in users if u["directory_id"] == dir_id]
        if active_only:
            users = [u for u in users if u["is_active"]]
        return users

    def create_group(self, dir_id: str, name: str, display_name: str = "", members: Optional[list[str]] = None) -> dict:
        group_id = str(uuid.uuid4())
        group = {"id": group_id, "directory_id": dir_id, "name": name, "display_name": display_name or name, "members": members or [], "is_active": True, "created_at": datetime.now(timezone.utc).isoformat(), "last_synced_at": datetime.now(timezone.utc).isoformat()}
        self._scim_groups[group_id] = group
        return group

    def update_group(self, group_id: str, updates: dict) -> Optional[dict]:
        group = self._scim_groups.get(group_id)
        if not group:
            return None
        for key in ("name", "display_name", "members", "is_active"):
            if key in updates:
                group[key] = updates[key]
        group["last_synced_at"] = datetime.now(timezone.utc).isoformat()
        return group

    def get_group(self, group_id: str) -> Optional[dict]:
        return self._scim_groups.get(group_id)

    def list_groups(self, dir_id: Optional[str] = None) -> list[dict]:
        groups = list(self._scim_groups.values())
        if dir_id:
            groups = [g for g in groups if g["directory_id"] == dir_id]
        return groups

    def sync_directory(self, dir_id: str) -> dict:
        directory = self._directories.get(dir_id)
        if not directory:
            return {"error": "Directory not found"}
        job_id = str(uuid.uuid4())
        job = {"id": job_id, "directory_id": dir_id, "status": "completed", "users_synced": len(self.list_users(dir_id)), "groups_synced": len(self.list_groups(dir_id)), "started_at": datetime.now(timezone.utc).isoformat(), "completed_at": datetime.now(timezone.utc).isoformat()}
        self._sync_jobs.append(job)
        directory["last_sync_at"] = datetime.now(timezone.utc).isoformat()
        directory["sync_status"] = "completed"
        return job

    def get_sync_jobs(self, dir_id: Optional[str] = None, limit: int = 10) -> list[dict]:
        jobs = list(self._sync_jobs)
        if dir_id:
            jobs = [j for j in jobs if j["directory_id"] == dir_id]
        return jobs[-limit:]

    def get_stats(self, org_id: str) -> dict:
        dirs = self.list_directories(org_id)
        dir_ids = [d["id"] for d in dirs]
        users = [u for u in self._scim_users.values() if u["directory_id"] in dir_ids]
        groups = [g for g in self._scim_groups.values() if g["directory_id"] in dir_ids]
        return {"directories": len(dirs), "users": len(users), "active_users": sum(1 for u in users if u["is_active"]), "groups": len(groups), "sync_jobs": len(self._sync_jobs)}


scim_service = SCIMService()
