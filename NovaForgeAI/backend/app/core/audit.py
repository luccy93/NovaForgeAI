"""Audit logging middleware — tracks all audit events to PostgreSQL."""

import logging
from typing import Optional, Callable, Awaitable
from uuid import UUID

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logging import get_logger
from app.models.support import AuditLog, AuditAction

logger = get_logger("novaforge.audit")

# Map URL paths to audit actions
PATH_ACTION_MAP: dict[str, AuditAction] = {
    "/api/v1/auth/login": AuditAction.LOGIN,
    "/api/v1/auth/register": AuditAction.REGISTER,
    "/api/v1/repositories": AuditAction.REPOSITORY_CREATE,
    "/api/v1/repositories/import": AuditAction.REPOSITORY_IMPORT,
}

MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await call_next(request)

        if request.method in MUTATING_METHODS and response.status_code < 400:
            await self._log_audit(request, response)

        return response

    async def _log_audit(self, request: Request, response: Response) -> None:
        action = self._resolve_action(request)
        if action is None:
            return

        try:
            from app.core.database import async_session
            async with async_session() as session:
                audit_entry = AuditLog(
                    action=action,
                    resource_type=self._resolve_resource_type(request),
                    resource_id=self._extract_resource_id(request),
                    details={
                        "method": request.method,
                        "path": str(request.url.path),
                        "status_code": response.status_code,
                    },
                    ip_address=request.client.host if request.client else None,
                    user_agent=request.headers.get("user-agent"),
                )
                session.add(audit_entry)
                await session.commit()
        except Exception as e:
            logger.warning("Failed to write audit log: %s", e)

    def _resolve_action(self, request: Request) -> Optional[AuditAction]:
        path = str(request.url.path)
        exact = PATH_ACTION_MAP.get(path)
        if exact:
            return exact

        if path.startswith("/api/v1/repositories/") and request.method == "DELETE":
            return AuditAction.REPOSITORY_DELETE
        if path.startswith("/api/v1/organizations/") and request.method == "DELETE":
            return AuditAction.ORGANIZATION_DELETE
        if "/permissions" in path:
            return AuditAction.PERMISSION_CHANGE
        return None

    def _resolve_resource_type(self, request: Request) -> Optional[str]:
        path = str(request.url.path)
        parts = [p for p in path.split("/") if p]
        for resource in ("repositories", "organizations", "users", "projects"):
            if resource in parts:
                return resource
        return None

    def _extract_resource_id(self, request: Request) -> Optional[str]:
        path = str(request.url.path)
        parts = [p for p in path.split("/") if p]
        for i, part in enumerate(parts):
            if part in ("repositories", "organizations", "users", "projects"):
                if i + 1 < len(parts):
                    return parts[i + 1]
        return None


def register_audit_middleware(app: FastAPI) -> None:
    app.add_middleware(AuditMiddleware)
