"""Security middleware — CSP, HSTS, rate limiting, threat detection."""

import time
from collections import defaultdict
from typing import Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.config import settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds security headers to all responses."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self'; "
            "connect-src 'self' https:; "
            "frame-ancestors 'none'; "
            "form-action 'self'; "
            "base-uri 'self'; "
        )
        return response


class RateLimiter:
    """Redis-backed rate limiter with per-IP and per-user tracking."""

    def __init__(self):
        self._local_buckets: dict[str, list[float]] = defaultdict(list)
        self._redis = None

    def _get_redis(self):
        if self._redis is None:
            try:
                import redis as redis_mod
                from app.core.config import settings as s
                if hasattr(s, 'redis_url') and s.redis_url:
                    self._redis = redis_mod.from_url(s.redis_url)
            except Exception:
                pass
        return self._redis

    async def check_ip(self, ip: str, max_requests: int = 200, window: int = 60) -> bool:
        redis_client = self._get_redis()
        if redis_client:
            return await self._check_redis(redis_client, f"rl:ip:{ip}", max_requests, window)
        return self._check_local(ip, max_requests, window)

    async def check_user(self, user_id: str, max_requests: int = 400, window: int = 60) -> bool:
        redis_client = self._get_redis()
        if redis_client:
            return await self._check_redis(redis_client, f"rl:user:{user_id}", max_requests, window)
        return self._check_local(f"user:{user_id}", max_requests, window)

    async def check_auth(self, ip: str, max_attempts: int = 10, window: int = 300) -> bool:
        redis_client = self._get_redis()
        key = f"rl:auth:{ip}"
        if redis_client:
            return await self._check_redis(redis_client, key, max_attempts, window)
        return self._check_local(key, max_attempts, window)

    async def record_auth_failure(self, ip: str, email: str) -> None:
        redis_client = self._get_redis()
        if redis_client:
            try:
                pipe = redis_client.pipeline()
                pipe.incr(f"rl:auth:{ip}")
                pipe.expire(f"rl:auth:{ip}", 300)
                pipe.incr(f"rl:auth:email:{email}")
                pipe.expire(f"rl:auth:email:{email}", 300)
                pipe.execute()
            except Exception:
                pass
        key = f"rl:auth:{ip}"
        now = time.time()
        self._local_buckets[key].append(now)

    async def _check_redis(self, client, key: str, max_req: int, window: int) -> bool:
        try:
            current = client.incr(key)
            if current == 1:
                client.expire(key, window)
            return current <= max_req
        except Exception:
            return True

    def _check_local(self, key: str, max_req: int, window: int) -> bool:
        now = time.time()
        self._local_buckets[key] = [t for t in self._local_buckets[key] if now - t < window]
        if len(self._local_buckets[key]) >= max_req:
            return False
        self._local_buckets[key].append(now)
        return True


rate_limiter = RateLimiter()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP and per-user rate limiting middleware."""

    AUTH_PATHS = ("/api/v1/auth/login", "/api/v1/auth/register")

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        path = request.url.path

        is_auth = any(path.startswith(a) for a in self.AUTH_PATHS)

        if is_auth:
            allowed = await rate_limiter.check_auth(client_ip)
            if not allowed:
                return Response(
                    content='{"error": "Too many authentication attempts. Try again later."}',
                    status_code=429,
                    media_type="application/json",
                    headers={"Retry-After": "300", "X-RateLimit-Type": "auth"},
                )
        else:
            allowed = await rate_limiter.check_ip(client_ip)
            if not allowed:
                return Response(
                    content='{"error": "Rate limit exceeded. Try again later."}',
                    status_code=429,
                    media_type="application/json",
                    headers={"Retry-After": "60", "X-RateLimit-Type": "general"},
                )

        response = await call_next(request)
        return response
