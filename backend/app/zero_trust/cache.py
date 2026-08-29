"""Redis cache layer — fallback to in-memory for tests."""

import json
from typing import Any, Optional

# In-memory fallback
_mem_cache: dict[str, tuple[str, float | None]] = {}

try:
    from app.core.redis import get_redis  # type: ignore

    _has_redis = True
except Exception:
    _has_redis = False


async def cache_get(key: str) -> Optional[str]:
    if _has_redis:
        try:
            redis = await get_redis()
            val = await redis.get(key)
            if val:
                return val if isinstance(val, str) else val.decode()  # type: ignore
        except Exception:
            pass
    # fallback
    entry = _mem_cache.get(key)
    if entry:
        return entry[0]
    return None


async def cache_set(key: str, value: str, ttl: int = 60) -> None:
    if _has_redis:
        try:
            redis = await get_redis()
            await redis.setex(key, ttl, value)
            return
        except Exception:
            pass
    _mem_cache[key] = (value, None)


async def cache_del(key: str) -> None:
    if _has_redis:
        try:
            redis = await get_redis()
            await redis.delete(key)
        except Exception:
            pass
    _mem_cache.pop(key, None)


async def cache_del_pattern(pattern: str) -> None:
    # For in-memory, delete keys starting with pattern without wildcard
    prefix = pattern.replace("*", "")
    keys = [k for k in list(_mem_cache.keys()) if k.startswith(prefix)]
    for k in keys:
        _mem_cache.pop(k, None)
    if _has_redis:
        try:
            redis = await get_redis()
            # Use scan
            cursor = "0"
            while True:
                cursor, keys = await redis.scan(cursor=cursor, match=pattern, count=100)
                if keys:
                    await redis.delete(*keys)
                if cursor == "0":
                    break
        except Exception:
            pass


def clear_mem_cache():
    _mem_cache.clear()
