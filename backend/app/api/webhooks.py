"""Webhook Management API — CRUD + event subscription mapping."""

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from app.api.auth import _get_current_user as get_current_user
from app.core.events import EventType
from app.core.webhooks import webhook_service

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


_webhooks: dict[str, dict] = {}


@router.post("/")
async def create_webhook(
    url: str = Body(...),
    events: list[str] = Body(...),
    secret: Optional[str] = Body(None),
    description: Optional[str] = Body(None),
    current_user: dict = Depends(get_current_user),
):
    valid_events = {e.value for e in EventType}
    for ev in events:
        if ev not in valid_events:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid event type: {ev}. Valid: {sorted(valid_events)}",
            )

    webhook = {
        "id": str(uuid.uuid4()),
        "url": url,
        "events": events,
        "secret": secret,
        "description": description or "",
        "created_by": str(getattr(current_user, "id", "unknown")),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "active": True,
    }
    _webhooks[webhook["id"]] = webhook
    return webhook


@router.get("/")
async def list_webhooks(
    current_user: dict = Depends(get_current_user),
):
    return list(_webhooks.values())


@router.get("/{webhook_id}")
async def get_webhook(
    webhook_id: str,
    current_user: dict = Depends(get_current_user),
):
    wh = _webhooks.get(webhook_id)
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return wh


@router.put("/{webhook_id}")
async def update_webhook(
    webhook_id: str,
    url: Optional[str] = Body(None),
    events: Optional[list[str]] = Body(None),
    active: Optional[bool] = Body(None),
    current_user: dict = Depends(get_current_user),
):
    wh = _webhooks.get(webhook_id)
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")

    if url is not None:
        wh["url"] = url
    if events is not None:
        valid_events = {e.value for e in EventType}
        for ev in events:
            if ev not in valid_events:
                raise HTTPException(
                    status_code=422,
                    detail=f"Invalid event type: {ev}",
                )
        wh["events"] = events
    if active is not None:
        wh["active"] = active
    return wh


@router.delete("/{webhook_id}")
async def delete_webhook(
    webhook_id: str,
    current_user: dict = Depends(get_current_user),
):
    if webhook_id not in _webhooks:
        raise HTTPException(status_code=404, detail="Webhook not found")
    del _webhooks[webhook_id]
    return {"status": "deleted"}


@router.get("/{webhook_id}/deliveries")
async def get_webhook_deliveries(
    webhook_id: str,
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    return await webhook_service.get_delivery_log(webhook_id, limit)


@router.get("/deliveries/dead-letter")
async def get_dead_letter_queue(
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    return await webhook_service.get_dead_letter_queue(limit)


@router.post("/deliveries/dead-letter/{index}/retry")
async def retry_dead_letter(
    index: int,
    current_user: dict = Depends(get_current_user),
):
    return await webhook_service.retry_dead_letter(index)
