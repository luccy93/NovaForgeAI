"""Health checks (Volume 35).

Separate liveness / readiness / startup / dependencies / deep health so
Kubernetes probes never run expensive checks and operators get a
measurable dependency view.

Endpoints:
    /health/live          - process alive (never touches dependencies)
    /health/startup       - application finished startup
    /health/ready         - core dependencies available (fast checks)
    /health/dependencies  - per-dependency status (medium cost)
    /health/deep          - full deep health (expensive; operator use only)
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from app.core.config import settings
from app.sre.constants import (
    DEPENDENCY_STATUS_DEGRADED,
    DEPENDENCY_STATUS_DOWN,
    DEPENDENCY_STATUS_HEALTHY,
    DEPENDENCY_STATUS_UNKNOWN,
    HEALTH_DEGRADED,
    HEALTH_HEALTHY,
    HEALTH_UNHEALTHY,
    HEALTH_UNKNOWN,
)
from app.sre.resilience import TimeoutPolicy, with_timeout

logger = logging.getLogger(__name__)


@dataclass
class CheckResult:
    name: str
    status: str = DEPENDENCY_STATUS_UNKNOWN
    latency_ms: float = 0.0
    detail: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status,
            "latency_ms": round(self.latency_ms, 2),
            "detail": self.detail,
            "metadata": self.metadata,
        }


CheckFn = Callable[[], Awaitable[tuple[bool, Optional[str], dict]]]


async def _check_db() -> tuple[bool, Optional[str], dict]:
    from app.core.database import check_db_connection

    ok = await check_db_connection()
    return ok, None if ok else "database unreachable", {}


async def _check_redis() -> tuple[bool, Optional[str], dict]:
    try:
        from app.core.redis import get_redis

        redis = await get_redis()
        await redis.ping()
        return True, None, {}
    except Exception as exc:
        return False, f"redis error: {exc}", {}


async def _check_qdrant() -> tuple[bool, Optional[str], dict]:
    try:
        from qdrant_client import QdrantClient  # noqa: PLC0415

        client = QdrantClient(url=settings.qdrant_url, prefer_grpc=False)
        collections = client.get_collections()
        count = len(collections.collections) if collections else 0
        return True, None, {"collections": count}
    except Exception as exc:
        return False, f"qdrant error: {exc}", {}


async def _check_neo4j() -> tuple[bool, Optional[str], dict]:
    try:
        from neo4j import GraphDatabase  # noqa: PLC0415

        driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        driver.verify_connectivity()
        driver.close()
        return True, None, {}
    except Exception as exc:
        return False, f"neo4j error: {exc}", {}


async def _check_object_storage() -> tuple[bool, Optional[str], dict]:
    """Object storage connectivity via env-configured S3-compatible endpoint."""
    import os

    endpoint = os.getenv("S3_ENDPOINT", "")
    if not endpoint:
        return True, "object storage not configured", {"configured": False}
    try:
        from urllib.request import urlopen, Request  # noqa: PLC0415

        req = Request(endpoint, method="HEAD")
        with urlopen(req, timeout=5):  # noqa: S310 - operator-configured internal endpoint
            return True, None, {"configured": True}
    except Exception as exc:
        return False, f"object storage error: {exc}", {"configured": True}


async def _check_event_bus() -> tuple[bool, Optional[str], dict]:
    try:
        from app.core.redis import get_redis

        redis = await get_redis()
        await redis.ping()
        return True, None, {}
    except Exception as exc:
        return False, f"event bus (redis) error: {exc}", {}


async def _check_ai_provider(provider: str = "openai") -> tuple[bool, Optional[str], dict]:
    key = getattr(settings, f"{provider}_api_key", None)
    if not key:
        return True, "no api key configured", {"configured": False}
    return True, None, {"configured": True}


DEFAULT_CHECKS: dict[str, CheckFn] = {
    "database": _check_db,
    "redis": _check_redis,
    "qdrant": _check_qdrant,
    "neo4j": _check_neo4j,
    "object_storage": _check_object_storage,
    "event_bus": _check_event_bus,
    "ai_provider": _check_ai_provider,
}

_FAST_CHECKS = ("database", "redis", "event_bus")
_STARTUP_CHECKS = ("database",)


class HealthChecker:
    """Runs dependency checks with per-check timeouts."""

    def __init__(self, registry: Optional[dict[str, CheckFn]] = None):
        self.checks: dict[str, CheckFn] = registry or dict(DEFAULT_CHECKS)
        self.startup_complete: bool = False
        self.started_at: float = time.monotonic()
        self.timeout_policy = TimeoutPolicy(overall_seconds=3.0)

    def register(self, name: str, check: CheckFn) -> None:
        self.checks[name] = check

    async def run(self, names: Optional[list[str]] = None) -> list[CheckResult]:
        targets = [n for n in (names or list(self.checks)) if n in self.checks]
        results: list[CheckResult] = []
        for name in targets:
            started = time.monotonic()
            try:
                ok, detail, meta = await with_timeout(
                    self.checks[name](), self.timeout_policy.overall_seconds, f"health:{name}"
                )
                status = DEPENDENCY_STATUS_HEALTHY if ok else DEPENDENCY_STATUS_DOWN
            except asyncio.TimeoutError:
                status, detail, meta = DEPENDENCY_STATUS_DOWN, "check timed out", {}
            except Exception as exc:
                status, detail, meta = DEPENDENCY_STATUS_DOWN, str(exc), {}
            results.append(
                CheckResult(name=name, status=status, latency_ms=(time.monotonic() - started) * 1000, detail=detail, metadata=meta)
            )
        return results

    def overall(self, results: list[CheckResult], required: Optional[list[str]] = None) -> str:
        required = required or []
        for result in results:
            if result.status == DEPENDENCY_STATUS_DOWN and result.name in required:
                return HEALTH_UNHEALTHY
        if any(r.status == DEPENDENCY_STATUS_DOWN for r in results):
            return HEALTH_DEGRADED
        if not results:
            return HEALTH_UNKNOWN
        return HEALTH_HEALTHY

    async def liveness(self) -> dict:
        return {"status": HEALTH_HEALTHY, "uptime_seconds": round(time.monotonic() - self.started_at, 2)}

    async def startup(self) -> dict:
        status = HEALTH_HEALTHY if self.startup_complete else "starting"
        return {"status": status, "startup_complete": self.startup_complete}

    def mark_started(self) -> None:
        self.startup_complete = True

    async def readiness(self) -> dict:
        results = await self.run(list(_FAST_CHECKS))
        status = self.overall(results, required=["database"])
        return {"status": status, "checks": {r.name: r.status for r in results}}

    async def dependencies(self) -> dict:
        results = await self.run()
        status = self.overall(results)
        return {
            "status": status,
            "checks": {r.name: r.to_dict() for r in results},
            "measured_at": time.time(),
        }

    async def deep(self) -> dict:
        """Full deep health; expensive - never use for k8s probes."""
        results = await self.run()
        return {
            "status": self.overall(results),
            "checks": {r.name: r.to_dict() for r in results},
            "detail": [r.to_dict() for r in results],
            "measured_at": time.time(),
        }


health_checker = HealthChecker()
