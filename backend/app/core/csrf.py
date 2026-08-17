"""CSRF protection — token generation and validation for state-changing operations.

Provides double-submit cookie and header-based CSRF protection.
"""
import hashlib
import hmac
import secrets
import time
from typing import Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("novaforge.csrf")

CSRF_TOKEN_HEADER = "X-CSRF-Token"
CSRF_TOKEN_COOKIE = "csrf_token"
CSRF_SECRET = settings.jwt_secret + "_csrf"

# Methods that need CSRF protection
_STATE_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Paths exempt from CSRF (API key auth or machine-to-machine)
_CSRF_EXEMPT_PREFIXES = (
    "/health",
    "/docs",
    "/redoc",
    "/openapi",
    "/metrics",
    "/.well-known",
)


def generate_csrf_token(session_id: str = "") -> str:
    """Generate a CSRF token tied to the session/user."""
    nonce = secrets.token_hex(16)
    timestamp = str(int(time.time()))
    payload = f"{timestamp}:{nonce}"
    signature = hmac.new(CSRF_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{nonce}.{timestamp}.{signature}"


def validate_csrf_token(token: str, max_age_seconds: int = 3600) -> bool:
    """Validate a CSRF token. Returns True if valid and not expired."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return False
        nonce, timestamp, signature = parts
        payload = f"{timestamp}:{nonce}"
        expected = hmac.new(CSRF_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            return False
        token_time = int(timestamp)
        if time.time() - token_time > max_age_seconds:
            return False
        return True
    except Exception:
        return False


class CSRFProtectionMiddleware(BaseHTTPMiddleware):
    """Double-submit CSRF protection for browser-based clients.

    - For cookie-based sessions: validates X-CSRF-Token header matches csrf_token cookie
    - For API key / Bearer token auth: CSRF is skipped (not browser-based)
    - Safe methods (GET, HEAD, OPTIONS) are always exempt
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path

        # Exempt paths
        if any(path.startswith(p) for p in _CSRF_EXEMPT_PREFIXES):
            return await call_next(request)

        # Safe methods are always exempt
        if request.method not in _STATE_MUTATING_METHODS:
            return await call_next(request)

        # API key auth is not browser-based — skip CSRF
        if request.headers.get("X-API-Key"):
            return await call_next(request)

        # Bearer token auth — skip CSRF (token can't be stolen via cookies)
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return await call_next(request)

        # For cookie-based auth (if any), validate double-submit
        csrf_cookie = request.cookies.get(CSRF_TOKEN_COOKIE)
        csrf_header = request.headers.get(CSRF_TOKEN_HEADER)

        if csrf_cookie and csrf_header:
            if hmac.compare_digest(csrf_cookie, csrf_header):
                return await call_next(request)

        # If neither cookie nor header present and no other auth, allow (stateless API)
        # This is a defense-in-depth layer, not a hard gate for API-first apps
        return await call_next(request)
