"""Admin console API — system overview, tenant management, health."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.models.organization import Organization, Subscription
from app.models.support import AgentRun, AuditLog, AnalyticsEvent
from app.schemas import AdminOverview, AdminOrganizationOut
from app.api.auth import _get_current_user, require_permission
from app.core.authorization import Permission

router = APIRouter()


async def _require_admin(
    current_user: User = Depends(_get_current_user),
) -> User:
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


@router.get("/overview", response_model=AdminOverview)
async def admin_overview(
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminOverview:
    org_count = await db.execute(select(func.count(Organization.id)))
    user_count = await db.execute(select(func.count(User.id)))
    repo_count = await db.execute(
        select(func.count()).select_from(text("repositories"))
    )
    active_subs = await db.execute(
        select(func.count(Subscription.id)).where(Subscription.status == "active")
    )
    agent_runs = await db.execute(select(func.count(AgentRun.id)))

    return AdminOverview(
        total_organizations=org_count.scalar() or 0,
        total_users=user_count.scalar() or 0,
        total_repositories=repo_count.scalar() or 0,
        active_subscriptions=active_subs.scalar() or 0,
        mrr_cents=0,
        total_agent_runs=agent_runs.scalar() or 0,
    )


@router.get("/organizations", response_model=list[AdminOrganizationOut])
async def admin_list_organizations(
    admin: User = Depends(_require_admin),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[AdminOrganizationOut]:
    result = await db.execute(
        select(Organization).order_by(Organization.created_at.desc()).offset(offset).limit(limit)
    )
    orgs = result.scalars().all()
    output = []
    for org in orgs:
        member_count = await db.execute(
            select(func.count()).select_from(text("user_organizations")).where(
                text("organization_id = :oid")
            ).params(oid=org.id.hex)
        )
        repo_count = await db.execute(
            select(func.count()).select_from(text("repositories")).where(
                text("organization_id = :oid")
            ).params(oid=org.id.hex)
        )
        output.append(AdminOrganizationOut(
            id=str(org.id),
            name=org.name,
            slug=org.slug,
            plan=org.plan,
            is_active=org.is_active,
            member_count=member_count.scalar() or 0,
            repository_count=repo_count.scalar() or 0,
            created_at=org.created_at,
        ))
    return output


@router.get("/users", response_model=list[dict])
async def admin_list_users(
    admin: User = Depends(_require_admin),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    result = await db.execute(
        select(User).order_by(User.created_at.desc()).offset(offset).limit(limit)
    )
    users = result.scalars().all()
    return [
        {
            "id": str(u.id),
            "email": u.email,
            "username": u.username,
            "is_active": u.is_active,
            "is_superuser": u.is_superuser,
            "created_at": u.created_at,
            "last_login_at": u.last_login_at,
        }
        for u in users
    ]


@router.get("/audit-log", response_model=list[dict])
async def admin_audit_log(
    admin: User = Depends(_require_admin),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    organization_id: Optional[str] = None,
    action: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
    if organization_id:
        try:
            oid = uuid.UUID(organization_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid organization_id")
        stmt = stmt.where(AuditLog.organization_id == oid)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    result = await db.execute(stmt)
    logs = result.scalars().all()
    return [
        {
            "id": str(log.id),
            "organization_id": str(log.organization_id) if log.organization_id else None,
            "user_id": str(log.user_id) if log.user_id else None,
            "action": log.action.value if hasattr(log.action, 'value') else str(log.action),
            "resource_type": log.resource_type,
            "resource_id": log.resource_id,
            "details": log.details,
            "ip_address": log.ip_address,
            "created_at": log.created_at,
        }
        for log in logs
    ]


@router.get("/analytics/events", response_model=list[dict])
async def admin_analytics_events(
    admin: User = Depends(_require_admin),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    event_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    stmt = select(AnalyticsEvent).order_by(AnalyticsEvent.created_at.desc()).offset(offset).limit(limit)
    if event_type:
        stmt = stmt.where(AnalyticsEvent.event_type == event_type)
    result = await db.execute(stmt)
    events = result.scalars().all()
    return [
        {
            "id": str(e.id),
            "organization_id": str(e.organization_id) if e.organization_id else None,
            "user_id": str(e.user_id) if e.user_id else None,
            "event_type": e.event_type,
            "event_name": e.event_name,
            "properties": e.properties,
            "created_at": e.created_at,
        }
        for e in events
    ]


@router.get("/feature-flags", response_model=list[dict])
async def admin_feature_flags(
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    from app.api.feature_flags import DEFAULT_FEATURE_FLAGS
    from app.models.support import FeatureFlag
    result = await db.execute(select(FeatureFlag).where(FeatureFlag.organization_id.is_(None)))
    overrides = {f.name: {"enabled": f.enabled, "config": f.config} for f in result.scalars().all()}
    return [
        {
            "name": name,
            "default": default,
            "overridden": name in overrides,
            "enabled": overrides[name]["enabled"] if name in overrides else default,
        }
        for name, default in DEFAULT_FEATURE_FLAGS.items()
    ]
