"""Governance evaluation cache — Volume 71 Commit 2.

Tenant/scope/version-keyed cache for immutable policy versions and
evaluation inputs. Every cached entry records the policy version it
was computed from; evaluation re-checks the current ACTIVE version
and re-evaluates on mismatch, so stale cache can never override a
newer mandatory deny. Invalidation on activation, retirement,
binding or exception change.
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
        raw = await cache_get(key, namespace="governance")
        if raw is not None:
            return json.loads(raw)
    except Exception:
        pass
    entry = _memory.get(f"governance:{key}")
    if entry and entry[0] > time.time():
        try:
            return json.loads(entry[1])
        except Exception:
            return None
    return None


async def cache_set_tenant(tenant: str, name: str, value: Any, scope: Optional[dict] = None,
                           ttl: int = 300) -> None:
    key = cache_key(tenant, name, scope)
    payload = json.dumps(value, default=str)
    try:
        from app.core.redis import cache_set
        await cache_set(key, payload, ttl=ttl, namespace="governance")
    except Exception:
        pass
    _memory[f"governance:{key}"] = (time.time() + ttl, payload)
    _key_registry.setdefault(tenant, set()).add(key)


async def cache_invalidate_tenant(tenant: str, name_prefix: str = "") -> int:
    count = 0
    keys = [k for k in _key_registry.get(tenant, set()) if name_prefix in k]
    try:
        from app.core.redis import cache_delete
        for key in keys:
            try:
                await cache_delete(key, namespace="governance")
            except Exception:
                pass
    except Exception:
        pass
    for key in keys:
        _memory.pop(f"governance:{key}", None)
        _key_registry.get(tenant, set()).discard(key)
        count += 1
    return count


async def cached_evaluate(db, tenant: str, *, scope_type: str, scope_value: str = "",
                          operation: str = "", context: Optional[dict] = None,
                          actor: str = "") -> dict:
    """Version-checked cached evaluation. Re-evaluates when the ACTIVE
    version set changed since the cached entry was stored."""
    from app.governance.plane_bindings import resolve_chain
    from app.governance.plane_evaluate import evaluate
    from app.governance.plane_policies import get_active_version

    scope = {"scope_type": scope_type, "scope_value": scope_value,
             "operation": operation, "context": context or {}}
    cached = await cache_get_tenant(tenant, "evaluate", scope)
    chain = await resolve_chain(db, tenant, scope_type, scope_value or "")
    current_versions = []
    for binding in chain:
        version = await get_active_version(db, tenant, binding["policy_id"])
        current_versions.append(f"{binding['policy_id']}:{version['id'] if version else 'none'}")
    fingerprint = hashlib.sha256(json.dumps(sorted(current_versions)).encode()).hexdigest()
    if cached is not None and cached.get("version_fingerprint") == fingerprint:
        try:
            from app.governance.plane_observability import record as _record
            await _record(db, tenant, "cache_hit", 1.0, {"endpoint": "evaluate"})
        except Exception:
            pass
        return {**cached["result"], "cached": True}
    result = await evaluate(db, tenant, scope_type=scope_type, scope_value=scope_value,
                            operation=operation, context=context, actor=actor)
    await cache_set_tenant(tenant, "evaluate",
                           {"result": result, "version_fingerprint": fingerprint},
                           scope, ttl=120)
    try:
        from app.governance.plane_observability import record as _record
        await _record(db, tenant, "cache_miss", 1.0, {"endpoint": "evaluate"})
    except Exception:
        pass
    return {**result, "cached": False}
