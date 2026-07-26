import time
import uuid
from collections import defaultdict
from typing import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.exceptions import NovaForgeError
from app.core.logging import get_logger, get_request_id_filter

logger = get_logger("novaforge.middleware")


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        get_request_id_filter().set_request_id(request_id)

        start_time = time.monotonic()
        response = await call_next(request)
        elapsed_ms = round((time.monotonic() - start_time) * 1000, 2)

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-Ms"] = str(elapsed_ms)

        logger.info("%s %s -> %d (%sms)", request.method, request.url.path, response.status_code, elapsed_ms)

        return response


class AuditLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            body = await request.body()
            logger.info("AUDIT method=%s path=%s body_size=%d", request.method, request.url.path, len(body))
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: FastAPI) -> None:
        super().__init__(app)
        self.default_limit = settings.rate_limit_default_max
        self.auth_limit = settings.rate_limit_auth_max
        self.window_seconds = settings.rate_limit_window_seconds
        self._store: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if request.url.path.startswith(("/health", "/docs", "/redoc", "/openapi")):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        window_start = now - self.window_seconds

        timestamps = self._store[client_ip]
        timestamps[:] = [t for t in timestamps if t > window_start]

        auth_paths = ("/api/v1/auth/login", "/api/v1/auth/register")
        limit = self.auth_limit if request.url.path.startswith(auth_paths) else self.default_limit

        if len(timestamps) >= limit:
            logger.warning("Rate limit exceeded for %s (%s)", client_ip, request.url.path)
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "RATE_LIMITED",
                        "message": f"Rate limit exceeded. Max {limit} requests per {self.window_seconds}s.",
                        "details": {"retry_after_seconds": self.window_seconds},
                    }
                },
                headers={"Retry-After": str(self.window_seconds)},
            )

        timestamps.append(now)
        return await call_next(request)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(NovaForgeError)
    async def novaforge_error_handler(request: Request, exc: NovaForgeError) -> JSONResponse:
        logger.warning("Handled error: %s %s -> %d %s", request.method, request.url.path, exc.status_code, exc.code)
        return JSONResponse(status_code=exc.status_code, content=exc.to_dict())

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception: %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred", "details": {}}},
        )


def register_middleware(app: FastAPI) -> None:
    app.add_middleware(AuditLogMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestIDMiddleware)
    register_exception_handlers(app)
