"""Redis utility layer — caching, rate limiting, queues, sessions.

All Redis interactions go through this module for consistency.
"""

import json
import logging
from typing import Any, Callable, Optional
from datetime import timedelta

from app.core.config import settings

logger = logging.getLogger(__name__)

_redis_client = None

# ─── Key Namespace Convention ─────────────────────────────────────────
# Format: {product}:{environment}:{namespace}:{key}
# Example: novaforge:prod:cache:repo:123

PREFIX = f"novaforge:{settings.app_version.split('.')[0]}"


def _key(namespace: str, key: str) -> str:
    return f"{PREFIX}:{namespace}:{key}"


_unavailable_until = 0.0
_UNAVAILABLE_COOLDOWN = 60.0


async def get_redis():
    """Lazy-init and return Redis client.

    Unavailability is cached briefly so best-effort callers do not pay a
    TCP timeout on every emission when no server is running.
    """
    global _redis_client, _unavailable_until
    if _redis_client is not None:
        return _redis_client
    try:
        import time as _time
        if _time.monotonic() < _unavailable_until:
            return None
    except Exception:
        pass
    try:
        import redis.asyncio as aioredis
        _redis_client = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=5,
            retry_on_timeout=True,
        )
        await _redis_client.ping()
        logger.info("Redis connected: %s", settings.redis_url)
    except Exception as e:
        logger.warning("Redis unavailable: %s. Using in-memory fallback.", e)
        _redis_client = None
        try:
            import time as _time
            _unavailable_until = _time.monotonic() + _UNAVAILABLE_COOLDOWN
        except Exception:
            pass
    return _redis_client


# ─── Cache ────────────────────────────────────────────────────────────

async def cache_get(key: str, namespace: str = "cache") -> Optional[str]:
    client = await get_redis()
    if client is None:
        return None
    try:
        return await client.get(_key(namespace, key))
    except Exception as e:
        logger.warning("Redis cache_get failed: %s", e)
        return None


async def cache_set(key: str, value: str, ttl: int = 300, namespace: str = "cache") -> bool:
    client = await get_redis()
    if client is None:
        return False
    try:
        await client.setex(_key(namespace, key), ttl, value)
        return True
    except Exception as e:
        logger.warning("Redis cache_set failed: %s", e)
        return False


async def cache_delete(key: str, namespace: str = "cache") -> bool:
    client = await get_redis()
    if client is None:
        return False
    try:
        await client.delete(_key(namespace, key))
        return True
    except Exception as e:
        logger.warning("Redis cache_delete failed: %s", e)
        return False


async def cached_result(ttl: int = 300, namespace: str = "cache"):
    """Decorator: cache the result of an async function."""
    def decorator(func: Callable) -> Callable:
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            cache_key = f"{func.__name__}:{str(args)}:{str(sorted(kwargs.items()))}"
            cached = await cache_get(cache_key, namespace)
            if cached is not None:
                return json.loads(cached)
            result = await func(*args, **kwargs)
            await cache_set(cache_key, json.dumps(result, default=str), ttl, namespace)
            return result
        return wrapper
    return decorator


# ─── Rate Limiting ────────────────────────────────────────────────────

async def rate_limit_check(key: str, max_requests: int, window_seconds: int = 60) -> tuple[bool, int]:
    """Check rate limit. Returns (allowed, remaining)."""
    client = await get_redis()
    if client is None:
        return True, max_requests  # fallback: allow

    try:
        redis_key = _key("ratelimit", key)
        current = await client.incr(redis_key)
        if current == 1:
            await client.expire(redis_key, window_seconds)
        ttl = await client.ttl(redis_key)
        remaining = max(0, max_requests - current)
        allowed = current <= max_requests
        return allowed, remaining
    except Exception as e:
        logger.warning("Rate limit check failed: %s", e)
        return True, max_requests


# ─── Session Store ────────────────────────────────────────────────────

async def session_set(session_id: str, data: dict, ttl: int = 3600) -> bool:
    return await cache_set(session_id, json.dumps(data), ttl, "session")


async def session_get(session_id: str) -> Optional[dict]:
    raw = await cache_get(session_id, "session")
    if raw:
        return json.loads(raw)
    return None


async def session_delete(session_id: str) -> bool:
    return await cache_delete(session_id, "session")


# ─── JWT Blacklist ────────────────────────────────────────────────────

async def blacklist_token(jti: str, expires_in: int = 3600) -> bool:
    return await cache_set(jti, "revoked", expires_in, "blacklist")


async def is_token_blacklisted(jti: str) -> bool:
    return await cache_get(jti, "blacklist") is not None


# ─── Distributed Locks ────────────────────────────────────────────────

async def acquire_lock(lock_name: str, ttl: int = 30) -> bool:
    client = await get_redis()
    if client is None:
        return True  # fallback
    try:
        result = await client.setnx(_key("lock", lock_name), "1")
        if result:
            await client.expire(_key("lock", lock_name), ttl)
        return bool(result)
    except Exception as e:
        logger.warning("Lock acquire failed: %s", e)
        return True


async def release_lock(lock_name: str) -> bool:
    return await cache_delete(lock_name, "lock")


# ─── Pub/Sub ──────────────────────────────────────────────────────────

async def publish(channel: str, message: Any) -> bool:
    client = await get_redis()
    if client is None:
        return False
    try:
        await client.publish(_key("pubsub", channel), json.dumps(message, default=str))
        return True
    except Exception as e:
        logger.warning("Redis publish failed: %s", e)
        return False
