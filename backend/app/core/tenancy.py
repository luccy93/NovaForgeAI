"""Multi-tenancy isolation layer.

Ensures every query is scoped to an organization.
Prevents cross-organization data leaks.
"""

import uuid
from typing import Optional, Callable, Awaitable

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy import select

from app.core.logging import get_logger

logger = get_logger("novaforge.tenancy")


class TenantContext:
    """Holds the current tenant (organization) context for the request."""

    _context: dict = {}

    @classmethod
    def set(cls, organization_id: Optional[uuid.UUID]) -> None:
        cls._context["organization_id"] = organization_id

    @classmethod
    def get(cls) -> Optional[uuid.UUID]:
        return cls._context.get("organization_id")

    @classmethod
    def clear(cls) -> None:
        cls._context.clear()

    @classmethod
    def get_filter(cls, model_org_column: str = "organization_id") -> Optional[tuple]:
        """Return a SQLAlchemy filter clause for the current tenant."""
        org_id = cls.get()
        if org_id is None:
            return None
        from sqlalchemy import text
        return (text(f"{model_org_column} = :tenant_org_id"), {"tenant_org_id": str(org_id)})


class TenantMiddleware(BaseHTTPMiddleware):
    """Extracts organization ID from request and sets tenant context."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        TenantContext.clear()

        org_id = self._extract_org_id(request)

        if org_id:
            TenantContext.set(org_id)
            request.state.organization_id = org_id

        response = await call_next(request)
        TenantContext.clear()
        return response

    def _extract_org_id(self, request: Request) -> Optional[uuid.UUID]:
        org_id = request.headers.get("X-Organization-ID")
        if org_id:
            try:
                return uuid.UUID(org_id)
            except ValueError:
                logger.warning("Invalid X-Organization-ID header: %s", org_id)
                return None

        path = str(request.url.path)
        parts = [p for p in path.split("/") if p]
        for i, part in enumerate(parts):
            if part == "organizations" and i + 1 < len(parts):
                try:
                    return uuid.UUID(parts[i + 1])
                except ValueError:
                    pass
        return None


def register_tenant_middleware(app: FastAPI) -> None:
    app.add_middleware(TenantMiddleware)
