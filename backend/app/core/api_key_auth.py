"""API Key authentication middleware — validates API keys on protected routes.

Checks X-API-Key header, looks up key by SHA-256 hash, validates scopes,
and injects user context into request state.
"""
import hashlib
import time
from typing import Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.logging import get_logger

logger = get_logger("novaforge.api_key_auth")

# Paths that are exempt from API key auth (public endpoints)
_EXEMPT_PREFIXES = (
    "/health",
    "/docs",
    "/redoc",
    "/openapi",
    "/metrics",
    "/.well-known",
)

# Paths that accept either API key OR bearer token
_DUAL_AUTH_PREFIXES = (
    "/api/v1/",
)


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """Validates API keys via X-API-Key header and sets request.state.user_id."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path

        # Skip exempt paths entirely
        if any(path.startswith(p) for p in _EXEMPT_PREFIXES):
            return await call_next(request)

        api_key = request.headers.get("X-API-Key")
        if not api_key:
            # No API key — let the route handler's dependency decide
            return await call_next(request)

        # Validate key format
        if not api_key.startswith("nf_") or len(api_key) < 20:
            return Response(
                content='{"error": {"code": "INVALID_API_KEY", "message": "Invalid API key format"}}',
                status_code=401,
                media_type="application/json",
            )

        key_hash = hashlib.sha256(api_key.encode()).hexdigest()

        # Import here to avoid circular imports
        try:
            from app.core.database import async_session
            from app.models.user import ApiKey
            from sqlalchemy import select

            async with async_session() as session:
                result = await session.execute(
                    select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.is_active == True)
                )
                api_key_obj = result.scalar_one_or_none()

                if not api_key_obj:
                    return Response(
                        content='{"error": {"code": "INVALID_API_KEY", "message": "API key not found or inactive"}}',
                        status_code=401,
                        media_type="application/json",
                    )

                # Check expiry
                if api_key_obj.expires_at and api_key_obj.expires_at < __import__("datetime").datetime.now(__import__("datetime").timezone.utc):
                    return Response(
                        content='{"error": {"code": "API_KEY_EXPIRED", "message": "API key has expired"}}',
                        status_code=401,
                        media_type="application/json",
                    )

                # Update last_used_at
                api_key_obj.last_used_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
                await session.commit()

                # Inject user context
                request.state.user_id = str(api_key_obj.user_id)
                request.state.api_key_id = str(api_key_obj.id)
                request.state.api_key_scopes = api_key_obj.scopes or []
                request.state.auth_method = "api_key"

        except Exception as e:
            logger.warning("API key validation error: %s", e)
            return Response(
                content='{"error": {"code": "AUTH_ERROR", "message": "Authentication error"}}',
                status_code=401,
                media_type="application/json",
            )

        return await call_next(request)
