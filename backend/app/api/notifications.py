"""Notification API — in-app list/read, channel management, preferences."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.models.support import Notification, NotificationChannel
from app.schemas import (
    NotificationOut,
    NotificationChannelCreate,
    NotificationChannelUpdate,
    NotificationChannelOut,
    NotificationPreferenceItem,
    NotificationPreferencesOut,
    NotificationEventType,
    NotificationChannelType,
)
from app.api.auth import _get_current_user
from app.services.notifications import (
    NotificationService,
    get_user_preferences,
    save_user_preferences,
    DEFAULT_PREFERENCES,
)

router = APIRouter()


# ─── In-App Notification ────────────────────────────────────────────────────

@router.get("", response_model=list[NotificationOut])
async def list_notifications(
    current_user: User = Depends(_get_current_user),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    unread_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
) -> list[NotificationOut]:
    stmt = select(Notification).where(Notification.user_id == current_user.id)
    if unread_only:
        stmt = stmt.where(Notification.is_read == False)
    stmt = stmt.order_by(Notification.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    return [
        NotificationOut(
            id=str(n.id),
            title=n.title,
            body=n.body,
            notification_type=n.notification_type,
            is_read=n.is_read,
            read_at=n.read_at,
            action_url=n.action_url,
            created_at=n.created_at,
        )
        for n in result.scalars().all()
    ]


@router.patch("/{notification_id}/read", response_model=NotificationOut)
async def mark_notification_read(
    notification_id: str,
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationOut:
    notif = await _get_notification_or_404(notification_id, current_user.id, db)
    notif.is_read = True
    notif.read_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(notif)
    return NotificationOut(
        id=str(notif.id),
        title=notif.title,
        body=notif.body,
        notification_type=notif.notification_type,
        is_read=notif.is_read,
        read_at=notif.read_at,
        action_url=notif.action_url,
        created_at=notif.created_at,
    )


@router.put("/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def mark_all_read(
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await db.execute(
        text("UPDATE notifications SET is_read = true, read_at = :now WHERE user_id = :uid AND is_read = false"),
        {"now": datetime.now(timezone.utc), "uid": current_user.id.hex},
    )


@router.get("/unread-count")
async def unread_count(
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        select(text("COUNT(*)")).select_from(Notification).where(
            Notification.user_id == current_user.id,
            Notification.is_read == False,
        )
    )
    return {"count": result.scalar()}


# ─── Notification Channels ──────────────────────────────────────────────────

@router.get("/channels", response_model=list[NotificationChannelOut])
async def list_channels(
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[NotificationChannelOut]:
    result = await db.execute(
        select(NotificationChannel).where(
            NotificationChannel.user_id == current_user.id
        ).order_by(NotificationChannel.created_at.desc())
    )
    return [
        NotificationChannelOut(
            id=str(ch.id),
            channel_type=ch.channel_type,
            name=ch.name,
            is_active=ch.is_active,
            verified_at=ch.verified_at,
            created_at=ch.created_at,
        )
        for ch in result.scalars().all()
    ]


@router.post("/channels", response_model=NotificationChannelOut, status_code=status.HTTP_201_CREATED)
async def create_channel(
    request: NotificationChannelCreate,
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationChannelOut:
    channel = NotificationChannel(
        user_id=current_user.id,
        channel_type=request.channel_type.value,
        name=request.name,
        config=request.config,
    )
    db.add(channel)
    await db.flush()
    await db.refresh(channel)
    return NotificationChannelOut(
        id=str(channel.id),
        channel_type=channel.channel_type,
        name=channel.name,
        is_active=channel.is_active,
        verified_at=channel.verified_at,
        created_at=channel.created_at,
    )


@router.patch("/channels/{channel_id}", response_model=NotificationChannelOut)
async def update_channel(
    channel_id: str,
    request: NotificationChannelUpdate,
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationChannelOut:
    ch = await _get_channel_or_404(channel_id, current_user.id, db)
    if request.name is not None:
        ch.name = request.name
    if request.config is not None:
        ch.config = request.config
    if request.is_active is not None:
        ch.is_active = request.is_active
    await db.flush()
    await db.refresh(ch)
    return NotificationChannelOut(
        id=str(ch.id),
        channel_type=ch.channel_type,
        name=ch.name,
        is_active=ch.is_active,
        verified_at=ch.verified_at,
        created_at=ch.created_at,
    )


@router.delete("/channels/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(
    channel_id: str,
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    ch = await _get_channel_or_404(channel_id, current_user.id, db)
    await db.delete(ch)


@router.post("/channels/{channel_id}/test")
async def test_channel(
    channel_id: str,
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    ch = await _get_channel_or_404(channel_id, current_user.id, db)
    svc = NotificationService(db)
    await svc._dispatch(ch, "Test Notification", "This is a test message from NovaForge.", None)
    return {"status": "sent"}


# ─── Preferences ────────────────────────────────────────────────────────────

@router.get("/preferences", response_model=NotificationPreferencesOut)
async def list_preferences(
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationPreferencesOut:
    prefs = await get_user_preferences(db, str(current_user.id))
    items = []
    for event_type in NotificationEventType:
        channels = prefs.get(event_type.value, ["in_app"])
        enabled = isinstance(channels, list) and len(channels) > 0
        items.append(NotificationPreferenceItem(
            event_type=event_type,
            channels=[NotificationChannelType(c) for c in channels if c in [t.value for t in NotificationChannelType]],
            enabled=enabled,
        ))
    return NotificationPreferencesOut(preferences=items)


@router.put("/preferences", response_model=NotificationPreferencesOut)
async def update_preferences(
    preferences: NotificationPreferencesOut,
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationPreferencesOut:
    prefs_dict = {}
    for item in preferences.preferences:
        if item.enabled and item.channels:
            prefs_dict[item.event_type.value] = [c.value for c in item.channels]
        else:
            prefs_dict[item.event_type.value] = []
    await save_user_preferences(db, str(current_user.id), prefs_dict)
    return preferences


# ─── Helpers ────────────────────────────────────────────────────────────────

async def _get_notification_or_404(notification_id: str, user_id: str, db: AsyncSession) -> Notification:
    try:
        nid = uuid.UUID(notification_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid notification_id")
    result = await db.execute(
        select(Notification).where(Notification.id == nid, Notification.user_id == user_id)
    )
    notif = result.scalar_one_or_none()
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")
    return notif


async def _get_channel_or_404(channel_id: str, user_id: str, db: AsyncSession) -> NotificationChannel:
    try:
        cid = uuid.UUID(channel_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid channel_id")
    result = await db.execute(
        select(NotificationChannel).where(NotificationChannel.id == cid, NotificationChannel.user_id == user_id)
    )
    ch = result.scalar_one_or_none()
    if not ch:
        raise HTTPException(status_code=404, detail="Notification channel not found")
    return ch
