"""Platform API — extensions, integrations, marketplace, and plugin orchestration."""

import json
import time
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.auth import _get_current_user as get_current_user
from app.core.events import Event, EventType, event_bus
from app.plugins.sdk import plugin_loader

router = APIRouter(prefix="/platform", tags=["platform"])


_extensions: dict[str, dict] = {}
_integrations: dict[str, dict] = {}


@router.get("/plugins")
async def list_plugins(current_user: dict = Depends(get_current_user)):
    return [
        {"name": name, "meta": plugin.meta.__dict__ if plugin.meta else {}}
        for name, plugin in plugin_loader.plugins.items()
    ]


@router.post("/plugins/{name}/enable")
async def enable_plugin(
    name: str,
    current_user: dict = Depends(get_current_user),
):
    if name not in plugin_loader.plugins:
        raise HTTPException(status_code=404, detail="Plugin not found")
    plugin = plugin_loader.plugins[name]
    try:
        plugin.initialize()
        plugin.on_startup()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "enabled", "plugin": name}


@router.post("/plugins/{name}/disable")
async def disable_plugin(
    name: str,
    current_user: dict = Depends(get_current_user),
):
    if name not in plugin_loader.plugins:
        raise HTTPException(status_code=404, detail="Plugin not found")
    plugin = plugin_loader.plugins[name]
    try:
        plugin.on_shutdown()
    except Exception:
        pass
    return {"status": "disabled", "plugin": name}


@router.post("/events/publish")
async def publish_event(
    event_type: str,
    payload: dict = {},
    current_user: dict = Depends(get_current_user),
):
    valid_types = {e.value for e in EventType}
    if event_type not in valid_types:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid event type: {event_type}. Valid: {sorted(valid_types)}",
        )
    await event_bus.publish(Event(EventType(event_type), payload))
    return {"status": "published", "event_type": event_type}


@router.get("/events/replay")
async def replay_events(
    event_type: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    if event_type:
        if event_type not in {e.value for e in EventType}:
            raise HTTPException(status_code=422, detail="Invalid event type")
        events = await event_bus.replay(EventType(event_type), limit)
    else:
        events = []
        for et in EventType:
            events.extend(await event_bus.replay(et, limit // len(EventType)))
    return {"events": events, "count": len(events)}


@router.post("/extensions")
async def register_extension(
    name: str,
    type: str,
    config: dict = {},
    current_user: dict = Depends(get_current_user),
):
    ext = {
        "id": str(uuid.uuid4()),
        "name": name,
        "type": type,
        "config": config,
        "registered_by": current_user.get("sub", "unknown"),
        "registered_at": time.time(),
    }
    _extensions[ext["id"]] = ext
    return ext


@router.get("/extensions")
async def list_extensions(
    type: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    results = list(_extensions.values())
    if type:
        results = [e for e in results if e["type"] == type]
    return results


@router.delete("/extensions/{ext_id}")
async def delete_extension(
    ext_id: str,
    current_user: dict = Depends(get_current_user),
):
    if ext_id not in _extensions:
        raise HTTPException(status_code=404, detail="Extension not found")
    del _extensions[ext_id]
    return {"status": "deleted"}


@router.post("/integrations")
async def create_integration(
    name: str,
    provider: str,
    credentials: dict = {},
    config: dict = {},
    current_user: dict = Depends(get_current_user),
):
    integration = {
        "id": str(uuid.uuid4()),
        "name": name,
        "provider": provider,
        "credentials": credentials,
        "config": config,
        "created_by": current_user.get("sub", "unknown"),
        "created_at": time.time(),
        "status": "active",
    }
    _integrations[integration["id"]] = integration
    return integration


@router.get("/integrations")
async def list_integrations(
    provider: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    results = list(_integrations.values())
    if provider:
        results = [i for i in results if i["provider"] == provider]
    return results


@router.delete("/integrations/{int_id}")
async def delete_integration(
    int_id: str,
    current_user: dict = Depends(get_current_user),
):
    if int_id not in _integrations:
        raise HTTPException(status_code=404, detail="Integration not found")
    del _integrations[int_id]
    return {"status": "deleted"}
