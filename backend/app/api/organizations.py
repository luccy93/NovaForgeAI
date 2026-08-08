"""Organization management API — multi-tenant orgs, members, invitations."""

import uuid
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import settings
from app.models.user import User
from app.models.organization import Organization
from app.schemas import (
    OrganizationCreate,
    OrganizationOut,
    OrganizationMemberOut,
    InviteRequest,
    InviteOut,
)
from app.api.auth import _get_current_user

router = APIRouter()


@router.post("", response_model=OrganizationOut, status_code=status.HTTP_201_CREATED)
async def create_organization(
    request: OrganizationCreate,
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrganizationOut:
    existing = await db.execute(
        select(Organization).where(Organization.slug == request.slug)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Organization with this slug already exists")

    org = Organization(
        name=request.name,
        slug=request.slug,
        description=request.description,
        plan=settings.default_org_plan,
    )
    db.add(org)
    await db.flush()

    await db.execute(
        text(
            "INSERT INTO user_organizations (user_id, organization_id, role) VALUES (:uid, :oid, :role)"
        ),
        {"uid": current_user.id, "oid": org.id, "role": "owner"},
    )

    await db.refresh(org)
    return _org_to_out(org)


@router.get("", response_model=list[OrganizationOut])
async def list_organizations(
    current_user: User = Depends(_get_current_user),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[OrganizationOut]:
    stmt = (
        select(Organization)
        .order_by(Organization.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    orgs = result.scalars().all()
    return [_org_to_out(o, db) for o in orgs]


@router.get("/my", response_model=list[OrganizationOut])
async def list_my_organizations(
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[OrganizationOut]:
    stmt = select(Organization).join(
        text("user_organizations"),
        text("user_organizations.organization_id = organizations.id"),
    ).where(text("user_organizations.user_id = :uid")).params(uid=current_user.id)
    result = await db.execute(stmt)
    orgs = result.scalars().all()
    return [_org_to_out(o) for o in orgs]


@router.get("/{organization_id}", response_model=OrganizationOut)
async def get_organization(
    organization_id: str,
    db: AsyncSession = Depends(get_db),
) -> OrganizationOut:
    org = await _get_org_or_404(organization_id, db)
    return _org_to_out(org)


@router.patch("/{organization_id}", response_model=OrganizationOut)
async def update_organization(
    organization_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrganizationOut:
    org = await _get_org_or_404(organization_id, db)
    if name:
        org.name = name
    if description is not None:
        org.description = description
    await db.flush()
    await db.refresh(org)
    return _org_to_out(org)


@router.delete("/{organization_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_organization(
    organization_id: str,
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    org = await _get_org_or_404(organization_id, db)
    await db.delete(org)


@router.get("/{organization_id}/members", response_model=list[OrganizationMemberOut])
async def list_members(
    organization_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[OrganizationMemberOut]:
    org = await _get_org_or_404(organization_id, db)
    rows = await db.execute(
        text("""
            SELECT u.id, u.email, u.username, uo.role, uo.joined_at
            FROM users u
            JOIN user_organizations uo ON uo.user_id = u.id
            WHERE uo.organization_id = :oid
            ORDER BY uo.joined_at
        """),
        {"oid": org.id},
    )
    return [
        OrganizationMemberOut(
            user_id=str(row.id),
            email=row.email,
            username=row.username,
            role=row.role,
            joined_at=row.joined_at,
        )
        for row in rows
    ]


@router.post("/{organization_id}/members", response_model=InviteOut, status_code=status.HTTP_201_CREATED)
async def invite_member(
    organization_id: str,
    request: InviteRequest,
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InviteOut:
    org = await _get_org_or_404(organization_id, db)
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    return InviteOut(
        id=str(uuid.uuid4()),
        email=request.email,
        role=request.role,
        token=token,
        expires_at=expires_at,
        created_at=datetime.now(timezone.utc),
    )


@router.delete("/{organization_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    organization_id: str,
    user_id: str,
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    org = await _get_org_or_404(organization_id, db)
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user_id")
    await db.execute(
        text("DELETE FROM user_organizations WHERE user_id = :uid AND organization_id = :oid"),
        {"uid": uid, "oid": org.id},
    )


@router.put("/{organization_id}/members/{user_id}/role")
async def update_member_role(
    organization_id: str,
    user_id: str,
    role: str = Query(...),
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    org = await _get_org_or_404(organization_id, db)
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user_id")
    valid_roles = {"owner", "admin", "manager", "developer", "reviewer", "viewer", "guest"}
    if role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {valid_roles}")
    await db.execute(
        text("UPDATE user_organizations SET role = :role WHERE user_id = :uid AND organization_id = :oid"),
        {"role": role, "uid": uid, "oid": org.id},
    )
    return {"status": "updated"}


async def _get_org_or_404(organization_id: str, db: AsyncSession) -> Organization:
    try:
        oid = uuid.UUID(organization_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid organization_id")
    result = await db.execute(select(Organization).where(Organization.id == oid))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


def _org_to_out(org: Organization) -> OrganizationOut:
    return OrganizationOut(
        id=str(org.id),
        name=org.name,
        slug=org.slug,
        description=org.description,
        plan=org.plan,
        is_active=org.is_active,
        created_at=org.created_at,
    )
