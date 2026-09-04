"""Tenant-bound integration read cache — Volume 70 Commit 2.

Caches derived reads (health summaries, policy evaluations) with TTL.
Keys embed tenant + scope hash so cached data can never cross tenants.
Redis when available with in-memory TTL fallback; PostgreSQL stays
authoritative.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Optional

_memory: dict[str, tuple[float, str]] = {}
_key_registry: dict[str, set[str]] = {}


def cache_key(tenant: str, name: str, scope: Optional[dict] = None) -> str:
    digest = hashlib.sha256(json.dumps(scope or {}, sort_keys=True, default=str).encode()).hexdigest()[:16]
    return f"{tenant}:{name}:{digest}"


async def cache_get_tenant(tenant: str, name: str, scope: Optional[dict] = None) -> Optional[Any]:
    key = cache_key(tenant, name, scope)
    try:
        from app.core.redis import cache_get
        raw = await cache_get(key, namespace="integrations")
        if raw is not None:
            return json.loads(raw)
    except Exception:
        pass
    entry = _memory.get(f"integrations:{key}")
    if entry and entry[0] > time.time():
        try:
            return json.loads(entry[1])
        except Exception:
            return None
    return None


async def cache_set_tenant(tenant: str, name: str, value: Any, scope: Optional[dict] = None, ttl: int = 300) -> None:
    key = cache_key(tenant, name, scope)
    payload = json.dumps(value, default=str)
    try:
        from app.core.redis import cache_set
        await cache_set(key, payload, ttl=ttl, namespace="integrations")
    except Exception:
        pass
    _memory[f"integrations:{key}"] = (time.time() + ttl, payload)
    _key_registry.setdefault(tenant, set()).add(key)


async def cache_invalidate_tenant(tenant: str, name_prefix: str = "") -> int:
    count = 0
    keys = [k for k in _key_registry.get(tenant, set()) if name_prefix in k]
    try:
        from app.core.redis import cache_delete
        for key in keys:
            try:
                await cache_delete(key, namespace="integrations")
            except Exception:
                pass
    except Exception:
        pass
    for key in keys:
        _memory.pop(f"integrations:{key}", None)
        _key_registry.get(tenant, set()).discard(key)
        count += 1
    return count
