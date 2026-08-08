"""
Multi-tenancy layer — Organization/Workspace/Project/Repository isolation.
"""
import logging
logger = logging.getLogger(__name__)

from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional
import json, uuid, hashlib, time
from collections import defaultdict
import os


class OrgTier(Enum):
    FREE = "free"
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"
    GOVERNMENT = "government"


class OrgStatus(Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    TRIAL = "trial"
    EXPIRED = "expired"
    DISABLED = "disabled"


class WorkspaceStatus(Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    FROZEN = "frozen"


class ProjectStatus(Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Organization:
    id: str
    name: str
    tier: OrgTier
    status: OrgStatus
    owner_id: str
    created_at: str
    updated_at: str
    settings: dict = field(default_factory=dict)
    features: list[str] = field(default_factory=list)
    max_workspaces: int = 5
    max_users: int = 10
    storage_quota_gb: int = 10
    custom_domain: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["tier"] = self.tier.value
        d["status"] = self.status.value
        return d

    @staticmethod
    def from_dict(data: dict) -> "Organization":
        data = dict(data)
        data["tier"] = OrgTier(data["tier"])
        data["status"] = OrgStatus(data["status"])
        return Organization(**data)


@dataclass
class Workspace:
    id: str
    org_id: str
    name: str
    description: str
    status: WorkspaceStatus
    created_at: str
    updated_at: str
    settings: dict = field(default_factory=dict)
    max_projects: int = 10
    region: str = "us-east-1"
    allowed_models: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @staticmethod
    def from_dict(data: dict) -> "Workspace":
        data = dict(data)
        data["status"] = WorkspaceStatus(data["status"])
        return Workspace(**data)


@dataclass
class Project:
    id: str
    workspace_id: str
    org_id: str
    name: str
    description: str
    status: ProjectStatus
    created_at: str
    updated_at: str
    settings: dict = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @staticmethod
    def from_dict(data: dict) -> "Project":
        data = dict(data)
        data["status"] = ProjectStatus(data["status"])
        return Project(**data)


@dataclass
class Repository:
    id: str
    project_id: str
    workspace_id: str
    org_id: str
    name: str
    description: str
    url: str
    default_branch: str
    is_private: bool
    created_at: str
    updated_at: str
    settings: dict = field(default_factory=dict)
    intelligence_enabled: bool = False
    knowledge_graph_enabled: bool = False
    embedding_enabled: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @staticmethod
    def from_dict(data: dict) -> "Repository":
        return Repository(**data)


# ---------------------------------------------------------------------------
# Managers
# ---------------------------------------------------------------------------

class OrganizationManager:
    """Manages organizations with JSON file persistence."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._orgs_file = os.path.join(storage_dir, "organizations.json")
        self._orgs: dict[str, Organization] = {}
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    # -- persistence --------------------------------------------------------

    def _load(self) -> None:
        try:
            if os.path.exists(self._orgs_file):
                with open(self._orgs_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._orgs = {
                    k: Organization.from_dict(v) for k, v in data.items()
                }
                logger.info("Loaded %d organizations from %s", len(self._orgs), self._orgs_file)
        except Exception:
            logger.exception("Failed to load organizations; starting fresh")
            self._orgs = {}

    def _save(self) -> None:
        try:
            data = {k: v.to_dict() for k, v in self._orgs.items()}
            tmp = self._orgs_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._orgs_file)
        except Exception:
            logger.exception("Failed to save organizations")

    # -- CRUD ---------------------------------------------------------------

    def create_organization(self, name: str, tier: OrgTier, owner_id: str,
                            max_workspaces: int = 5, max_users: int = 10,
                            storage_quota_gb: int = 10,
                            custom_domain: Optional[str] = None) -> Organization:
        try:
            for org in self._orgs.values():
                if org.name == name:
                    raise ValueError(f"Organization with name '{name}' already exists")

            now = datetime.now(timezone.utc).isoformat()
            org = Organization(
                id=str(uuid.uuid4()),
                name=name,
                tier=tier,
                status=OrgStatus.TRIAL if tier == OrgTier.FREE else OrgStatus.ACTIVE,
                owner_id=owner_id,
                created_at=now,
                updated_at=now,
                max_workspaces=max_workspaces,
                max_users=max_users,
                storage_quota_gb=storage_quota_gb,
                custom_domain=custom_domain,
            )
            self._orgs[org.id] = org
            self._save()
            self.telemetry["organizations_created"] += 1
            logger.info("Created organization %s (%s)", org.id, name)
            return org
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to create organization")
            raise

    def get_organization(self, org_id: str) -> Organization:
        org = self._orgs.get(org_id)
        if org is None:
            raise ValueError(f"Organization not found: {org_id}")
        self.telemetry["organizations_read"] += 1
        return org

    def update_organization(self, org_id: str, **kwargs) -> Organization:
        try:
            org = self.get_organization(org_id)
            for key, val in kwargs.items():
                if hasattr(org, key) and key not in ("id", "created_at"):
                    setattr(org, key, val)
            org.updated_at = datetime.now(timezone.utc).isoformat()
            self._orgs[org_id] = org
            self._save()
            self.telemetry["organizations_updated"] += 1
            return org
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to update organization %s", org_id)
            raise

    def delete_organization(self, org_id: str) -> None:
        try:
            if org_id not in self._orgs:
                raise ValueError(f"Organization not found: {org_id}")
            del self._orgs[org_id]
            self._save()
            self.telemetry["organizations_deleted"] += 1
            logger.info("Deleted organization %s", org_id)
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to delete organization %s", org_id)
            raise

    def list_organizations(self, status: Optional[OrgStatus] = None) -> list[Organization]:
        try:
            orgs = list(self._orgs.values())
            if status is not None:
                orgs = [o for o in orgs if o.status == status]
            self.telemetry["organizations_listed"] += 1
            return orgs
        except Exception:
            logger.exception("Failed to list organizations")
            raise

    def suspend_organization(self, org_id: str) -> Organization:
        return self.update_organization(org_id, status=OrgStatus.SUSPENDED)

    def activate_organization(self, org_id: str) -> Organization:
        return self.update_organization(org_id, status=OrgStatus.ACTIVE)

    def update_tier(self, org_id: str, new_tier: OrgTier) -> Organization:
        return self.update_organization(org_id, tier=new_tier)

    def get_usage_stats(self, org_id: str) -> dict:
        try:
            org = self.get_organization(org_id)
            return {
                "org_id": org.id,
                "org_name": org.name,
                "tier": org.tier.value,
                "status": org.status.value,
                "max_workspaces": org.max_workspaces,
                "max_users": org.max_users,
                "storage_quota_gb": org.storage_quota_gb,
                "custom_domain": org.custom_domain,
                "features": list(org.features),
            }
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to get usage stats for %s", org_id)
            raise


class WorkspaceManager:
    """Manages workspaces with JSON persistence and org-limit enforcement."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._ws_file = os.path.join(storage_dir, "workspaces.json")
        self._workspaces: dict[str, Workspace] = {}
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    # -- persistence --------------------------------------------------------

    def _load(self) -> None:
        try:
            if os.path.exists(self._ws_file):
                with open(self._ws_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._workspaces = {
                    k: Workspace.from_dict(v) for k, v in data.items()
                }
                logger.info("Loaded %d workspaces", len(self._workspaces))
        except Exception:
            logger.exception("Failed to load workspaces; starting fresh")
            self._workspaces = {}

    def _save(self) -> None:
        try:
            data = {k: v.to_dict() for k, v in self._workspaces.items()}
            tmp = self._ws_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._ws_file)
        except Exception:
            logger.exception("Failed to save workspaces")

    # -- CRUD ---------------------------------------------------------------

    def create_workspace(self, org_id: str, name: str, description: str = "",
                         max_projects: int = 10, region: str = "us-east-1",
                         allowed_models: Optional[list[str]] = None,
                         org_manager: Optional[OrganizationManager] = None) -> Workspace:
        try:
            if org_manager is not None:
                org = org_manager.get_organization(org_id)
                existing = self._count_by_org(org_id)
                if existing >= org.max_workspaces:
                    raise ValueError(
                        f"Organization '{org_id}' has reached its max workspaces "
                        f"({org.max_workspaces})"
                    )

            for ws in self._workspaces.values():
                if ws.org_id == org_id and ws.name == name:
                    raise ValueError(f"Workspace '{name}' already exists in org '{org_id}'")

            now = datetime.now(timezone.utc).isoformat()
            ws = Workspace(
                id=str(uuid.uuid4()),
                org_id=org_id,
                name=name,
                description=description,
                status=WorkspaceStatus.ACTIVE,
                created_at=now,
                updated_at=now,
                max_projects=max_projects,
                region=region,
                allowed_models=allowed_models or [],
            )
            self._workspaces[ws.id] = ws
            self._save()
            self.telemetry["workspaces_created"] += 1
            logger.info("Created workspace %s in org %s", ws.id, org_id)
            return ws
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to create workspace")
            raise

    def get_workspace(self, workspace_id: str) -> Workspace:
        ws = self._workspaces.get(workspace_id)
        if ws is None:
            raise ValueError(f"Workspace not found: {workspace_id}")
        self.telemetry["workspaces_read"] += 1
        return ws

    def update_workspace(self, workspace_id: str, **kwargs) -> Workspace:
        try:
            ws = self.get_workspace(workspace_id)
            for key, val in kwargs.items():
                if hasattr(ws, key) and key not in ("id", "org_id", "created_at"):
                    setattr(ws, key, val)
            ws.updated_at = datetime.now(timezone.utc).isoformat()
            self._workspaces[workspace_id] = ws
            self._save()
            self.telemetry["workspaces_updated"] += 1
            return ws
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to update workspace %s", workspace_id)
            raise

    def delete_workspace(self, workspace_id: str) -> None:
        try:
            if workspace_id not in self._workspaces:
                raise ValueError(f"Workspace not found: {workspace_id}")
            del self._workspaces[workspace_id]
            self._save()
            self.telemetry["workspaces_deleted"] += 1
            logger.info("Deleted workspace %s", workspace_id)
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to delete workspace %s", workspace_id)
            raise

    def list_workspaces(self, org_id: Optional[str] = None,
                        status: Optional[WorkspaceStatus] = None) -> list[Workspace]:
        try:
            results = list(self._workspaces.values())
            if org_id is not None:
                results = [w for w in results if w.org_id == org_id]
            if status is not None:
                results = [w for w in results if w.status == status]
            self.telemetry["workspaces_listed"] += 1
            return results
        except Exception:
            logger.exception("Failed to list workspaces")
            raise

    def archive_workspace(self, workspace_id: str) -> Workspace:
        return self.update_workspace(workspace_id, status=WorkspaceStatus.ARCHIVED)

    def freeze_workspace(self, workspace_id: str) -> Workspace:
        return self.update_workspace(workspace_id, status=WorkspaceStatus.FROZEN)

    def can_create_project(self, workspace_id: str) -> bool:
        try:
            ws = self.get_workspace(workspace_id)
            if ws.status != WorkspaceStatus.ACTIVE:
                return False
            return True
        except ValueError:
            return False
        except Exception:
            logger.exception("Error checking project creation permission")
            return False

    # -- internal helpers ---------------------------------------------------

    def _count_by_org(self, org_id: str) -> int:
        return sum(1 for w in self._workspaces.values() if w.org_id == org_id)


class ProjectManager:
    """Manages projects with JSON persistence."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._proj_file = os.path.join(storage_dir, "projects.json")
        self._projects: dict[str, Project] = {}
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    # -- persistence --------------------------------------------------------

    def _load(self) -> None:
        try:
            if os.path.exists(self._proj_file):
                with open(self._proj_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._projects = {
                    k: Project.from_dict(v) for k, v in data.items()
                }
                logger.info("Loaded %d projects", len(self._projects))
        except Exception:
            logger.exception("Failed to load projects; starting fresh")
            self._projects = {}

    def _save(self) -> None:
        try:
            data = {k: v.to_dict() for k, v in self._projects.items()}
            tmp = self._proj_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._proj_file)
        except Exception:
            logger.exception("Failed to save projects")

    # -- CRUD ---------------------------------------------------------------

    def create_project(self, workspace_id: str, org_id: str, name: str,
                       description: str = "", tags: Optional[list[str]] = None,
                       workspace_manager: Optional[WorkspaceManager] = None) -> Project:
        try:
            if workspace_manager is not None:
                ws = workspace_manager.get_workspace(workspace_id)
                if ws.status != WorkspaceStatus.ACTIVE:
                    raise ValueError(
                        f"Cannot create project in workspace with status {ws.status.value}"
                    )
                existing = self._count_by_workspace(workspace_id)
                if existing >= ws.max_projects:
                    raise ValueError(
                        f"Workspace '{workspace_id}' has reached max projects ({ws.max_projects})"
                    )

            for proj in self._projects.values():
                if proj.workspace_id == workspace_id and proj.name == name:
                    raise ValueError(f"Project '{name}' already exists in workspace '{workspace_id}'")

            now = datetime.now(timezone.utc).isoformat()
            project = Project(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                org_id=org_id,
                name=name,
                description=description,
                status=ProjectStatus.ACTIVE,
                created_at=now,
                updated_at=now,
                tags=tags or [],
            )
            self._projects[project.id] = project
            self._save()
            self.telemetry["projects_created"] += 1
            logger.info("Created project %s in workspace %s", project.id, workspace_id)
            return project
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to create project")
            raise

    def get_project(self, project_id: str) -> Project:
        proj = self._projects.get(project_id)
        if proj is None:
            raise ValueError(f"Project not found: {project_id}")
        self.telemetry["projects_read"] += 1
        return proj

    def update_project(self, project_id: str, **kwargs) -> Project:
        try:
            proj = self.get_project(project_id)
            for key, val in kwargs.items():
                if hasattr(proj, key) and key not in ("id", "workspace_id", "org_id", "created_at"):
                    setattr(proj, key, val)
            proj.updated_at = datetime.now(timezone.utc).isoformat()
            self._projects[project_id] = proj
            self._save()
            self.telemetry["projects_updated"] += 1
            return proj
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to update project %s", project_id)
            raise

    def delete_project(self, project_id: str) -> None:
        try:
            if project_id not in self._projects:
                raise ValueError(f"Project not found: {project_id}")
            del self._projects[project_id]
            self._save()
            self.telemetry["projects_deleted"] += 1
            logger.info("Deleted project %s", project_id)
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to delete project %s", project_id)
            raise

    def list_projects(self, workspace_id: Optional[str] = None,
                      org_id: Optional[str] = None,
                      status: Optional[ProjectStatus] = None) -> list[Project]:
        try:
            results = list(self._projects.values())
            if workspace_id is not None:
                results = [p for p in results if p.workspace_id == workspace_id]
            if org_id is not None:
                results = [p for p in results if p.org_id == org_id]
            if status is not None:
                results = [p for p in results if p.status == status]
            self.telemetry["projects_listed"] += 1
            return results
        except Exception:
            logger.exception("Failed to list projects")
            raise

    def archive_project(self, project_id: str) -> Project:
        return self.update_project(project_id, status=ProjectStatus.ARCHIVED)

    def complete_project(self, project_id: str) -> Project:
        return self.update_project(project_id, status=ProjectStatus.COMPLETED)

    # -- internal helpers ---------------------------------------------------

    def _count_by_workspace(self, workspace_id: str) -> int:
        return sum(1 for p in self._projects.values() if p.workspace_id == workspace_id)


class TenancyManager(OrganizationManager, WorkspaceManager, ProjectManager):
    """Unified multi-tenancy manager combining org, workspace, and project management."""

    def __init__(self, storage_dir: str):
        OrganizationManager.__init__(self, storage_dir)
        WorkspaceManager.__init__(self, storage_dir)
        ProjectManager.__init__(self, storage_dir)
        self.telemetry: dict = defaultdict(int)
        logger.info("TenancyManager initialized at %s", storage_dir)

    def verify_isolation(self, org_id: str, workspace_id: str, project_id: str) -> bool:
        try:
            org = self.get_organization(org_id)
            ws = self.get_workspace(workspace_id)
            proj = self.get_project(project_id)

            if ws.org_id != org.id:
                logger.warning("Isolation breach: workspace %s not in org %s", workspace_id, org_id)
                return False
            if proj.workspace_id != ws.id:
                logger.warning("Isolation breach: project %s not in workspace %s", project_id, workspace_id)
                return False
            if proj.org_id != org.id:
                logger.warning("Isolation breach: project %s org_id mismatch", project_id)
                return False

            self.telemetry["isolation_checks_passed"] += 1
            return True
        except ValueError:
            self.telemetry["isolation_checks_failed"] += 1
            return False
        except Exception:
            logger.exception("Error during isolation verification")
            self.telemetry["isolation_checks_failed"] += 1
            return False

    def generate_tenant_report(self, org_id: str) -> dict:
        try:
            org = self.get_organization(org_id)
            workspaces = self.list_workspaces(org_id=org_id)
            total_projects = 0
            workspace_details = []

            for ws in workspaces:
                projects = self.list_projects(workspace_id=ws.id)
                total_projects += len(projects)
                workspace_details.append({
                    "workspace_id": ws.id,
                    "workspace_name": ws.name,
                    "status": ws.status.value,
                    "project_count": len(projects),
                    "projects": [
                        {"id": p.id, "name": p.name, "status": p.status.value}
                        for p in projects
                    ],
                })

            report = {
                "org_id": org.id,
                "org_name": org.name,
                "tier": org.tier.value,
                "status": org.status.value,
                "workspace_count": len(workspaces),
                "project_count": total_projects,
                "max_workspaces": org.max_workspaces,
                "max_users": org.max_users,
                "storage_quota_gb": org.storage_quota_gb,
                "workspaces": workspace_details,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "isolation_verified": all(
                    self.verify_isolation(org_id, ws.id, p.id)
                    for ws in workspaces
                    for p in self.list_projects(workspace_id=ws.id)
                ),
            }

            self.telemetry["reports_generated"] += 1
            return report
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to generate tenant report for %s", org_id)
            raise
