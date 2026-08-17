"""SCIM Provisioning Service — Volume 40.

SCIM 2.0-style provisioning for users, groups, membership,
deprovisioning, and directory synchronization.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


class SCIMDirectoryRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    organization_id: str
    provider: str
    base_url: str
    is_active: bool = True
    sync_status: str = "pending"
    last_sync_at: Optional[str] = None
    last_sync_error: str = ""
    users_synced: int = 0
    groups_synced: int = 0
    config: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SCIMUserRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    directory_id: str
    organization_id: str
    user_id: str = ""
    external_id: str
    username: str
    email: str = ""
    display_name: str = ""
    active: bool = True
    groups: list[str] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    raw_scim: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SCIMGroupRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    directory_id: str
    organization_id: str
    external_id: str
    display_name: str
    members: list[str] = Field(default_factory=list)
    mapped_role: str = ""
    mapped_workspace_ids: list[str] = Field(default_factory=list)
    mapped_project_ids: list[str] = Field(default_factory=list)
    mapped_policies: list[str] = Field(default_factory=list)
    raw_scim: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SCIMSyncResult(BaseModel):
    directory_id: str
    users_synced: int = 0
    users_created: int = 0
    users_updated: int = 0
    users_deactivated: int = 0
    groups_synced: int = 0
    groups_created: int = 0
    groups_updated: int = 0
    errors: list[str] = Field(default_factory=list)
    started_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str = ""


class SCIMService:
    """In-memory SCIM provisioning service."""

    _instance: Optional["SCIMService"] = None

    def __new__(cls) -> "SCIMService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._directories: dict[str, SCIMDirectoryRecord] = {}
        self._users: dict[str, SCIMUserRecord] = {}
        self._groups: dict[str, SCIMGroupRecord] = {}
        self._sync_results: list[SCIMSyncResult] = []
        self._initialized = True

    def reset(self) -> None:
        self._directories.clear()
        self._users.clear()
        self._groups.clear()
        self._sync_results.clear()

    # ── Directory Management ────────────────────────────────────────────

    def create_directory(
        self,
        organization_id: str,
        provider: str,
        base_url: str,
        config: dict[str, Any] | None = None,
    ) -> SCIMDirectoryRecord:
        d = SCIMDirectoryRecord(
            organization_id=organization_id,
            provider=provider,
            base_url=base_url,
            config=config or {},
        )
        self._directories[d.id] = d
        return d

    def get_directory(self, directory_id: str) -> Optional[SCIMDirectoryRecord]:
        return self._directories.get(directory_id)

    def list_directories(self, organization_id: str | None = None) -> list[SCIMDirectoryRecord]:
        results = list(self._directories.values())
        if organization_id:
            results = [d for d in results if d.organization_id == organization_id]
        return results

    def delete_directory(self, directory_id: str) -> bool:
        if directory_id not in self._directories:
            return False
        del self._directories[directory_id]
        self._users = {k: v for k, v in self._users.items() if v.directory_id != directory_id}
        self._groups = {k: v for k, v in self._groups.items() if v.directory_id != directory_id}
        return True

    # ── User Provisioning ──────────────────────────────────────────────

    def provision_user(
        self,
        directory_id: str,
        organization_id: str,
        external_id: str,
        username: str,
        email: str = "",
        display_name: str = "",
        active: bool = True,
        groups: list[str] | None = None,
        raw_scim: dict[str, Any] | None = None,
    ) -> SCIMUserRecord:
        for user in self._users.values():
            if user.directory_id == directory_id and user.external_id == external_id:
                user.username = username
                user.email = email
                user.display_name = display_name
                user.active = active
                user.groups = groups or user.groups
                user.raw_scim = raw_scim or user.raw_scim
                user.updated_at = datetime.now(timezone.utc).isoformat()
                return user
        user = SCIMUserRecord(
            directory_id=directory_id,
            organization_id=organization_id,
            external_id=external_id,
            username=username,
            email=email,
            display_name=display_name,
            active=active,
            groups=groups or [],
            raw_scim=raw_scim or {},
        )
        self._users[user.id] = user
        return user

    def get_user(self, user_id: str) -> Optional[SCIMUserRecord]:
        return self._users.get(user_id)

    def find_user_by_external_id(self, directory_id: str, external_id: str) -> Optional[SCIMUserRecord]:
        for user in self._users.values():
            if user.directory_id == directory_id and user.external_id == external_id:
                return user
        return None

    def list_users(
        self,
        directory_id: str | None = None,
        organization_id: str | None = None,
        active_only: bool = False,
    ) -> list[SCIMUserRecord]:
        results = list(self._users.values())
        if directory_id:
            results = [u for u in results if u.directory_id == directory_id]
        if organization_id:
            results = [u for u in results if u.organization_id == organization_id]
        if active_only:
            results = [u for u in results if u.active]
        return results

    def deactivate_user(self, directory_id: str, external_id: str) -> Optional[SCIMUserRecord]:
        user = self.find_user_by_external_id(directory_id, external_id)
        if not user:
            return None
        user.active = False
        user.updated_at = datetime.now(timezone.utc).isoformat()
        return user

    def deprovision_user(self, user_id: str) -> Optional[SCIMUserRecord]:
        user = self._users.get(user_id)
        if not user:
            return None
        user.active = False
        user.groups = []
        user.updated_at = datetime.now(timezone.utc).isoformat()
        return user

    # ── Group Provisioning ─────────────────────────────────────────────

    def provision_group(
        self,
        directory_id: str,
        organization_id: str,
        external_id: str,
        display_name: str,
        members: list[str] | None = None,
        mapped_role: str = "",
        raw_scim: dict[str, Any] | None = None,
    ) -> SCIMGroupRecord:
        for group in self._groups.values():
            if group.directory_id == directory_id and group.external_id == external_id:
                group.display_name = display_name
                group.members = members or group.members
                group.mapped_role = mapped_role or group.mapped_role
                group.raw_scim = raw_scim or group.raw_scim
                group.updated_at = datetime.now(timezone.utc).isoformat()
                return group
        group = SCIMGroupRecord(
            directory_id=directory_id,
            organization_id=organization_id,
            external_id=external_id,
            display_name=display_name,
            members=members or [],
            mapped_role=mapped_role,
            raw_scim=raw_scim or {},
        )
        self._groups[group.id] = group
        return group

    def get_group(self, group_id: str) -> Optional[SCIMGroupRecord]:
        return self._groups.get(group_id)

    def find_group_by_external_id(self, directory_id: str, external_id: str) -> Optional[SCIMGroupRecord]:
        for group in self._groups.values():
            if group.directory_id == directory_id and group.external_id == external_id:
                return group
        return None

    def list_groups(
        self,
        directory_id: str | None = None,
        organization_id: str | None = None,
    ) -> list[SCIMGroupRecord]:
        results = list(self._groups.values())
        if directory_id:
            results = [g for g in results if g.directory_id == directory_id]
        if organization_id:
            results = [g for g in results if g.organization_id == organization_id]
        return results

    def sync_groups_from_directory(
        self,
        directory_id: str,
        groups_data: list[dict[str, Any]],
    ) -> SCIMSyncResult:
        result = SCIMSyncResult(directory_id=directory_id)
        directory = self._directories.get(directory_id)
        if not directory:
            result.errors.append(f"Directory {directory_id} not found")
            return result

        existing_external_ids = {
            g.external_id for g in self._groups.values() if g.directory_id == directory_id
        }
        seen_external_ids = set()

        for group_data in groups_data:
            ext_id = group_data.get("external_id", "")
            seen_external_ids.add(ext_id)
            try:
                self.provision_group(
                    directory_id=directory_id,
                    organization_id=directory.organization_id,
                    external_id=ext_id,
                    display_name=group_data.get("displayName", ""),
                    members=group_data.get("members", []),
                    mapped_role=group_data.get("mapped_role", ""),
                    raw_scim=group_data,
                )
                if ext_id in existing_external_ids:
                    result.groups_updated += 1
                else:
                    result.groups_created += 1
                result.groups_synced += 1
            except Exception as e:
                result.errors.append(f"Group sync error ({ext_id}): {str(e)}")

        directory.groups_synced = result.groups_synced
        directory.last_sync_at = datetime.now(timezone.utc).isoformat()
        directory.sync_status = "completed" if not result.errors else "completed_with_errors"
        result.completed_at = datetime.now(timezone.utc).isoformat()
        self._sync_results.append(result)
        return result

    def delete_group(self, group_id: str) -> bool:
        if group_id not in self._groups:
            return False
        del self._groups[group_id]
        return True

    # ── Deprovisioning ─────────────────────────────────────────────────

    def deprovision_all_for_directory(self, directory_id: str) -> dict[str, int]:
        users_deactivated = 0
        groups_deleted = 0
        for user in self._users.values():
            if user.directory_id == directory_id and user.active:
                user.active = False
                user.groups = []
                user.updated_at = datetime.now(timezone.utc).isoformat()
                users_deactivated += 1
        groups_to_delete = [g_id for g_id, g in self._groups.items() if g.directory_id == directory_id]
        for g_id in groups_to_delete:
            del self._groups[g_id]
            groups_deleted += 1
        return {"users_deactivated": users_deactivated, "groups_deleted": groups_deleted}

    # ── Metrics ─────────────────────────────────────────────────────────

    def get_metrics(self, organization_id: str | None = None) -> dict[str, Any]:
        directories = self.list_directories(organization_id)
        users = self.list_users(organization_id=organization_id)
        groups = self.list_groups(organization_id=organization_id)
        return {
            "directories": len(directories),
            "active_directories": sum(1 for d in directories if d.is_active),
            "total_users": len(users),
            "active_users": sum(1 for u in users if u.active),
            "total_groups": len(groups),
            "sync_results": len(self._sync_results),
        }
