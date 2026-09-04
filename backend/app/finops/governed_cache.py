"""Tenant-bound FinOps read cache — Volume 69 Commit 2.

Caches derived read models (summaries, comparisons) with TTL. Keys always
embed the tenant and a hash of the query scope, so cached data can never
leak across tenants. Redis is used when available with an in-memory
TTL fallback; authoritative cost/budget state always lives in PostgreSQL.
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
        raw = await cache_get(key, namespace="finops")
        if raw is not None:
            return json.loads(raw)
    except Exception:
        pass
    entry = _memory.get(f"finops:{key}")
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
        await cache_set(key, payload, ttl=ttl, namespace="finops")
    except Exception:
        pass
    _memory[f"finops:{key}"] = (time.time() + ttl, payload)
    _key_registry.setdefault(tenant, set()).add(key)


async def cache_invalidate_tenant(tenant: str, name_prefix: str = "") -> int:
    count = 0
    keys = [k for k in _key_registry.get(tenant, set()) if name_prefix in k]
    try:
        from app.core.redis import cache_delete
        for key in keys:
            try:
                await cache_delete(key, namespace="finops")
            except Exception:
                pass
    except Exception:
        pass
    for key in keys:
        _memory.pop(f"finops:{key}", None)
        _key_registry.get(tenant, set()).discard(key)
        count += 1
    return count
