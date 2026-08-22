"""Rate limiter — per-tenant, per-user, per-API-key, per-endpoint rate limiting."""
from __future__ import annotations
import time
from typing import Optional
from app.iam.config import get_iam_config


class RateLimiter:
    def __init__(self):
        self._buckets: dict[str, dict] = {}
        self._config = get_iam_config()
        self._blocked: dict[str, float] = {}

    def check(self, key: str, limit: Optional[int] = None, window_seconds: int = 60) -> dict:
        now = time.time()
        blocked_until = self._blocked.get(key, 0)
        if now < blocked_until:
            return {"allowed": False, "reason": "temporarily_blocked", "retry_after": int(blocked_until - now)}
        limit = limit or self._config.rate_limit_requests_per_minute
        bucket = self._buckets.get(key)
        if not bucket or now - bucket["window_start"] > window_seconds:
            self._buckets[key] = {"count": 1, "window_start": now, "limit": limit}
            return {"allowed": True, "remaining": limit - 1, "limit": limit, "reset_at": int(now + window_seconds)}
        bucket["count"] += 1
        if bucket["count"] > limit:
            return {"allowed": False, "reason": "rate_limit_exceeded", "limit": limit, "remaining": 0, "retry_after": window_seconds - int(now - bucket["window_start"])}
        return {"allowed": True, "remaining": limit - bucket["count"], "limit": limit, "reset_at": int(bucket["window_start"] + window_seconds)}

    def check_tenant(self, org_id: str, endpoint: str = "default", limit: Optional[int] = None) -> dict:
        return self.check(f"tenant:{org_id}:{endpoint}", limit)

    def check_user(self, user_id: str, endpoint: str = "default", limit: Optional[int] = None) -> dict:
        return self.check(f"user:{user_id}:{endpoint}", limit)

    def check_api_key(self, key_id: str, endpoint: str = "default", limit: Optional[int] = None) -> dict:
        return self.check(f"apikey:{key_id}:{endpoint}", limit)

    def check_service_account(self, sa_id: str, endpoint: str = "default", limit: Optional[int] = None) -> dict:
        return self.check(f"sa:{sa_id}:{endpoint}", limit)

    def block(self, key: str, duration_seconds: int = 900) -> None:
        self._blocked[key] = time.time() + duration_seconds

    def unblock(self, key: str) -> bool:
        if key in self._blocked:
            del self._blocked[key]
            return True
        return False

    def reset(self, key: str) -> bool:
        if key in self._buckets:
            del self._buckets[key]
            return True
        return False

    def get_usage(self, key: str) -> dict:
        bucket = self._buckets.get(key)
        if not bucket:
            return {"key": key, "count": 0, "limit": self._config.rate_limit_requests_per_minute}
        return {"key": key, "count": bucket["count"], "limit": bucket["limit"], "window_start": int(bucket["window_start"])}

    def cleanup(self, max_age_seconds: int = 300) -> int:
        now = time.time()
        count = 0
        expired_keys = [k for k, v in self._buckets.items() if now - v["window_start"] > max_age_seconds]
        for k in expired_keys:
            del self._buckets[k]
            count += 1
        expired_blocked = [k for k, v in self._blocked.items() if now > v]
        for k in expired_blocked:
            del self._blocked[k]
        return count

    def get_stats(self) -> dict:
        return {"active_buckets": len(self._buckets), "blocked_keys": len(self._blocked)}


rate_limiter = RateLimiter()
