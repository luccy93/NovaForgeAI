"""Marketplace API — plugin listing, search, install tracking."""

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.auth import _get_current_user as get_current_user

router = APIRouter(prefix="/marketplace", tags=["marketplace"])


PLUGIN_STORE = {
    "nova-debugger": {
        "id": "nova-debugger",
        "name": "Nova Debugger",
        "description": "Step-through debugger for agent workflows",
        "version": "1.0.0",
        "author": "NovaForge",
        "category": "developer-tools",
        "price": 0,
        "downloads": 1200,
        "rating": 4.5,
        "created_at": "2026-01-15T00:00:00Z",
    },
    "nova-monitor": {
        "id": "nova-monitor",
        "name": "Nova Monitor",
        "description": "Real-time monitoring and alerts for production agents",
        "version": "1.2.0",
        "author": "NovaForge",
        "category": "monitoring",
        "price": 1999,
        "downloads": 850,
        "rating": 4.7,
        "created_at": "2026-02-01T00:00:00Z",
    },
    "code-analyzer-pro": {
        "id": "code-analyzer-pro",
        "name": "Code Analyzer Pro",
        "description": "Advanced static analysis with security vulnerability scanning",
        "version": "2.0.0",
        "author": "Community",
        "category": "code-analysis",
        "price": 4999,
        "downloads": 3200,
        "rating": 4.3,
        "created_at": "2025-11-10T00:00:00Z",
    },
    "git-automation": {
        "id": "git-automation",
        "name": "Git Automation",
        "description": "Automated PR reviews, merge conflict resolution, changelog generation",
        "version": "1.3.1",
        "author": "Community",
        "category": "automation",
        "price": 0,
        "downloads": 5400,
        "rating": 4.8,
        "created_at": "2026-03-05T00:00:00Z",
    },
}


_installations: dict[str, list] = {}


@router.get("/plugins")
async def list_plugins(
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    results = list(PLUGIN_STORE.values())

    if category:
        results = [p for p in results if p["category"] == category]
    if search:
        q = search.lower()
        results = [
            p for p in results
            if q in p["name"].lower() or q in p["description"].lower()
        ]

    start = (page - 1) * page_size
    end = start + page_size
    return {
        "items": results[start:end],
        "total": len(results),
        "page": page,
        "page_size": page_size,
    }


@router.get("/plugins/{plugin_id}")
async def get_plugin(plugin_id: str):
    plugin = PLUGIN_STORE.get(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail="Plugin not found")
    return plugin


@router.post("/plugins/{plugin_id}/install")
async def install_plugin(
    plugin_id: str,
    org_id: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    plugin = PLUGIN_STORE.get(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail="Plugin not found")

    key = f"{org_id}:{plugin_id}"
    if key in _installations:
        raise HTTPException(status_code=409, detail="Plugin already installed")

    install = {
        "id": str(uuid.uuid4()),
        "plugin_id": plugin_id,
        "org_id": org_id,
        "installed_by": current_user.get("sub", "unknown"),
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "config": {},
        "enabled": True,
    }
    _installations[key] = install
    return install


@router.post("/plugins/{plugin_id}/uninstall")
async def uninstall_plugin(
    plugin_id: str,
    org_id: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    key = f"{org_id}:{plugin_id}"
    if key not in _installations:
        raise HTTPException(status_code=404, detail="Plugin not installed")
    del _installations[key]
    return {"status": "uninstalled"}


@router.get("/installations")
async def list_installations(
    org_id: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    return [
        v for k, v in _installations.items()
        if k.startswith(f"{org_id}:")
    ]


@router.get("/categories")
async def list_categories():
    cats = set()
    for p in PLUGIN_STORE.values():
        cats.add(p["category"])
    return sorted(cats)
