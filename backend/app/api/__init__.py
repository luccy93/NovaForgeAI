"""NovaForge Unified API — FastAPI application factory and assembly."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from app.api.router import api_router
from app.api.volumes import router as volumes_router
from app.core.config import settings
from app.core.database import check_db_connection
from app.core.logging import configure_logging
from app.core.middleware import register_middleware, register_exception_handlers
from app.core.audit import register_audit_middleware
from app.core.tenancy import register_tenant_middleware
from app.core.security_middleware import SecurityHeadersMiddleware, RateLimitMiddleware as SecurityRateLimitMiddleware
from app.core.csrf import CSRFProtectionMiddleware
from app.core.api_key_auth import APIKeyAuthMiddleware

logger = logging.getLogger("novaforge")

configure_logging(settings.log_level)


@asynccontextmanager
async def _lifespan(application: FastAPI):
    """Startup: health readiness signal, SRE workers, catalog seeding, webhook bridge."""
    from app.sre.health import health_checker
    from app.sre.otel import setup_otel
    from app.sre.workers import workers
    from app.core.webhook_bridge import webhook_bridge

    setup_otel()
    health_checker.mark_started()
    if not settings.testing:
        try:
            workers.start()
        except Exception as exc:
            logger.warning("SRE workers failed to start: %s", exc)

    # Start webhook event bridge
    from app.api.webhooks import _webhooks
    webhook_bridge.set_webhook_store(_webhooks)
    try:
        await webhook_bridge.start()
    except Exception as exc:
        logger.warning("Webhook bridge failed to start: %s", exc)

    try:
        yield
    finally:
        await webhook_bridge.stop()
        await workers.stop()


def create_app() -> FastAPI:
    application = FastAPI(
        title="NovaForge",
        version=settings.app_version,
        docs_url="/docs",
        openapi_url="/openapi.json",
        lifespan=_lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.get("/health")
    async def health() -> dict:
        return {"status": "ok", "version": settings.app_version}

    @application.get("/health/live")
    async def health_live() -> dict:
        from app.sre.health import health_checker

        return await health_checker.liveness()

    @application.get("/health/startup")
    async def health_startup() -> dict:
        from app.sre.health import health_checker

        return await health_checker.startup()

    @application.get("/health/ready")
    async def health_ready() -> dict:
        from app.sre.health import health_checker

        results = await health_checker.readiness()
        # Backward-compatible response: original consumers expect
        # checks.app + checks.database; extended checks are additive.
        checks = {"app": True}
        for name, status in results.get("checks", {}).items():
            checks[name] = status == "healthy"
        return {"status": results.get("status"), "checks": checks}

    @application.get("/health/dependencies")
    async def health_dependencies() -> dict:
        from app.sre.health import health_checker

        return await health_checker.dependencies()

    @application.get("/health/deep")
    async def health_deep() -> dict:
        from app.sre.health import health_checker

        return await health_checker.deep()

    @application.get("/metrics")
    async def metrics() -> Response:
        from app.sre.metrics import render_metrics

        body, content_type = render_metrics()
        return Response(content=body, media_type=content_type)

    application.include_router(api_router)
    application.include_router(volumes_router)
    register_middleware(application)
    register_exception_handlers(application)
    register_audit_middleware(application)
    register_tenant_middleware(application)
    application.add_middleware(SecurityHeadersMiddleware)
    application.add_middleware(APIKeyAuthMiddleware)
    application.add_middleware(CSRFProtectionMiddleware)
    return application


app = create_app()