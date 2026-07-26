import enum
from typing import Optional
from pydantic import BaseModel


class OrgRole(str, enum.Enum):
    owner = "owner"
    admin = "admin"
    member = "member"
    viewer = "viewer"


class Permission(str, enum.Enum):
    read_repo = "read:repo"
    write_repo = "write:repo"
    delete_repo = "delete:repo"
    manage_members = "manage:members"
    manage_settings = "manage:settings"
    run_agents = "run:agents"
    run_pipeline = "run:pipeline"
    view_analytics = "view:analytics"
    admin_all = "admin:all"


ROLE_PERMISSIONS: dict[OrgRole, set[Permission]] = {
    OrgRole.owner: {
        Permission.read_repo,
        Permission.write_repo,
        Permission.delete_repo,
        Permission.manage_members,
        Permission.manage_settings,
        Permission.run_agents,
        Permission.run_pipeline,
        Permission.view_analytics,
        Permission.admin_all,
    },
    OrgRole.admin: {
        Permission.read_repo,
        Permission.write_repo,
        Permission.delete_repo,
        Permission.manage_members,
        Permission.run_agents,
        Permission.run_pipeline,
        Permission.view_analytics,
    },
    OrgRole.member: {
        Permission.read_repo,
        Permission.write_repo,
        Permission.run_agents,
        Permission.run_pipeline,
        Permission.view_analytics,
    },
    OrgRole.viewer: {
        Permission.read_repo,
        Permission.view_analytics,
    },
}


class MembershipInfo(BaseModel):
    user_id: str
    organization_id: str
    role: OrgRole
