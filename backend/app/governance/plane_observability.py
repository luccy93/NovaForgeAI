"""Governance observability — Volume 71 Commit 2.

Structured counters through existing observability plumbing
(best-effort) plus secret-free structured logs. Measures evaluations,
allow/deny ratio inputs, latency, cache hit/miss, violations,
exceptions, control failures, drift and evidence freshness.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


async def record(db, tenant: str, metric: str, value: float = 1.0,
                 tags: Optional[dict] = None) -> None:
    safe_tags = {str(k): str(v)[:128] for k, v in (tags or {}).items()}
    logger.info("governance metric tenant=%s metric=%s value=%s tags=%s",
                tenant, metric, value, safe_tags)
    try:
        from app.observability.platform import platform_service
        await platform_service.ingest_metric(
            db, tenant, metric=f"governance.{metric}", type="counter",
            value=float(value), tags=safe_tags)
    except Exception:
        pass


class Timer:
    def __init__(self, db, tenant: str, metric: str, tags: Optional[dict] = None):
        self._db = db
        self._tenant = tenant
        self._metric = metric
        self._tags = tags or {}
        self._started = time.monotonic()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        elapsed_ms = (time.monotonic() - self._started) * 1000
        await record(self._db, self._tenant, self._metric, elapsed_ms, self._tags)
