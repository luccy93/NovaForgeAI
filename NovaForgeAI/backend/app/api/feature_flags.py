"""Feature flag management API endpoints."""

import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import settings
from app.models.user import User
from app.models.support import FeatureFlag
from app.schemas import FeatureFlagOut, FeatureFlagUpdate
from app.api.auth import _get_current_user, require_permission
from app.core.authorization import Permission

router = APIRouter()


@router.get("", response_model=list[FeatureFlagOut])
async def list_feature_flags(
    organization_id: Optional[str] = None,
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[FeatureFlagOut]:
    stmt = select(FeatureFlag)
    if organization_id:
        try:
            oid = uuid.UUID(organization_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid organization_id")
        stmt = stmt.where(
            (FeatureFlag.organization_id == oid) | (FeatureFlag.organization_id.is_(None))
        )
    else:
        stmt = stmt.where(FeatureFlag.organization_id.is_(None))
    result = await db.execute(stmt.order_by(FeatureFlag.name))
    flags = result.scalars().all()
    return [
        FeatureFlagOut(
            id=str(f.id),
            name=f.name,
            enabled=f.enabled,
            config=f.config or {},
            organization_id=str(f.organization_id) if f.organization_id else None,
        )
        for f in flags
    ]


@router.get("/{flag_name}", response_model=FeatureFlagOut)
async def get_feature_flag(
    flag_name: str,
    organization_id: Optional[str] = None,
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FeatureFlagOut:
    stmt = select(FeatureFlag).where(FeatureFlag.name == flag_name)
    if organization_id:
        try:
            oid = uuid.UUID(organization_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid organization_id")
        stmt = stmt.where(FeatureFlag.organization_id == oid)
    else:
        stmt = stmt.where(FeatureFlag.organization_id.is_(None))
    result = await db.execute(stmt)
    flag = result.scalar_one_or_none()
    if not flag:
        raise HTTPException(status_code=404, detail="Feature flag not found")
    return FeatureFlagOut(
        id=str(flag.id),
        name=flag.name,
        enabled=flag.enabled,
        config=flag.config or {},
        organization_id=str(flag.organization_id) if flag.organization_id else None,
    )


@router.put("/{flag_name}", response_model=FeatureFlagOut)
async def update_feature_flag(
    flag_name: str,
    update: FeatureFlagUpdate,
    organization_id: Optional[str] = None,
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FeatureFlagOut:
    stmt = select(FeatureFlag).where(FeatureFlag.name == flag_name)
    if organization_id:
        try:
            oid = uuid.UUID(organization_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid organization_id")
        stmt = stmt.where(FeatureFlag.organization_id == oid)
    else:
        stmt = stmt.where(FeatureFlag.organization_id.is_(None))
    result = await db.execute(stmt)
    flag = result.scalar_one_or_none()
    if not flag:
        flag = FeatureFlag(
            name=flag_name,
            organization_id=uuid.UUID(organization_id) if organization_id else None,
            enabled=update.enabled,
            config=update.config or {},
        )
        db.add(flag)
    else:
        flag.enabled = update.enabled
        if update.config is not None:
            flag.config = update.config
    await db.flush()
    await db.refresh(flag)
    return FeatureFlagOut(
        id=str(flag.id),
        name=flag.name,
        enabled=flag.enabled,
        config=flag.config or {},
        organization_id=str(flag.organization_id) if flag.organization_id else None,
    )


DEFAULT_FEATURE_FLAGS = {
    "ai_chat": True,
    "code_review": True,
    "repository_import": True,
    "multi_agent": False,
    "github_webhooks": True,
    "analytics_dashboard": True,
    "sso_saml": False,
    "audit_logs": True,
    "api_keys": True,
    "plugins": False,
    "marketplace": False,
    "team_workspaces": False,
}


async def is_feature_enabled(
    flag_name: str,
    db: AsyncSession,
    organization_id: Optional[str] = None,
) -> bool:
    default = DEFAULT_FEATURE_FLAGS.get(flag_name, False)
    if organization_id:
        try:
            oid = uuid.UUID(organization_id)
        except ValueError:
            return default
        result = await db.execute(
            select(FeatureFlag).where(
                FeatureFlag.name == flag_name,
                FeatureFlag.organization_id == oid,
            )
        )
        flag = result.scalar_one_or_none()
        if flag:
            return flag.enabled
    result = await db.execute(
        select(FeatureFlag).where(
            FeatureFlag.name == flag_name,
            FeatureFlag.organization_id.is_(None),
        )
    )
    flag = result.scalar_one_or_none()
    return flag.enabled if flag else default
