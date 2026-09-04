"""Integration workers — Volume 70 Commit 1.

Lease-guarded, idempotent background execution following the ai_dev
worker conventions: API execution through managed connections,
webhook delivery retries, and bounded health checks.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.common import (
    ValidationError,
    _as_uuid,
    _utcnow,
    idempotency_key as make_idempotency_key,
    sanitize_metadata,
)
from app.integrations.governed_models import (
    Integration,
    IntegrationAuditLog,
    IntegrationConnection,
    IntegrationExecution,
    IntegrationHealthCheck,
    IntegrationWebhookDelivery,
)

logger = logging.getLogger(__name__)

_leases: dict[str, dict] = {}


def _worker_id() -> str:
    return f"integrations-worker-{uuid.uuid4().hex[:8]}"


async def acquire_lease(tenant: str, job_key: str, worker_id: str, ttl_seconds: int = 300) -> bool:
    now = _utcnow()
    key = f"{tenant}:{job_key}"
    lease = _leases.get(key)
    if lease and lease["expires_at"] > now and lease["worker_id"] != worker_id:
        return False
    from datetime import timedelta
    _leases[key] = {"worker_id": worker_id, "acquired_at": now,
                    "expires_at": now + timedelta(seconds=ttl_seconds)}
    return True


async def release_lease(tenant: str, job_key: str, worker_id: str) -> None:
    key = f"{tenant}:{job_key}"
    lease = _leases.get(key)
    if lease and lease["worker_id"] == worker_id:
        _leases.pop(key, None)


def _serialize_execution(row: IntegrationExecution) -> dict:
    return {
        "id": str(row.id),
        "tenant": row.tenant,
        "connection_id": str(row.connection_id),
        "operation": row.operation or "",
        "method": row.method,
        "endpoint_ref": row.endpoint_ref or "",
        "status": row.status,
        "attempts": row.attempts,
        "latency_ms": row.latency_ms,
        "request_bytes": row.request_bytes,
        "response_bytes": row.response_bytes,
        "idempotency_key": row.idempotency_key,
        "error": row.error or "",
    }


async def execute_operation(
    db: AsyncSession, tenant: str, connection_id, operation: str, *,
    method: str = "GET", path: str = "", params: Optional[dict] = None,
    body: Optional[bytes] = None, idempotency_key: str = "",
    timeout: float = 15.0, actor: str = "",
) -> dict:
    """Execute an allowed API operation through a managed connection.

    Authentication comes only from the connection's stored credential;
    caller headers are never trusted. Destructive methods require an
    explicit per-connection allowlist.
    """
    from app.integrations.connections import record_connection_result, resolve_credential_material
    from app.integrations.outbound import execute as outbound

    if not tenant:
        raise ValidationError("tenant required")
    stmt = select(IntegrationConnection).where(
        IntegrationConnection.id == _as_uuid(connection_id),
        IntegrationConnection.tenant == tenant,
    )
    connection = (await db.execute(stmt)).scalar_one_or_none()
    if connection is None:
        raise ValidationError("connection not found")
    if connection.status != "ACTIVE":
        raise ValidationError(f"connection is {connection.status}")

    method = (method or "GET").upper()
    allowed = ((connection.metadata_ or {}).get("allowed_methods") if connection.metadata_ else None) or ["GET", "POST"]
    if method not in allowed:
        raise ValidationError(f"method {method} not allowed for this connection")
    if not (1.0 <= float(timeout or 0) <= 120.0):
        raise ValidationError("timeout must be 1-120s")

    base = (connection.endpoint_ref or "").rstrip("/")
    target = f"{base}/{str(path or '').lstrip('/')}" if path else base
    if params:
        from urllib.parse import urlencode
        target = f"{target}?{urlencode({k: str(v)[:256] for k, v in params.items()})}"

    headers: dict[str, str] = {}
    managed_auth: Optional[dict] = None
    if connection.credential_id:
        material = await resolve_credential_material(
            db, tenant, connection.credential_id, purpose="api_execution", actor=actor)
        auth_cfg = ((await _credential_auth_config(db, tenant, connection.credential_id)) or {})
        if auth_cfg.get("header") and material:
            managed_auth = {"header": str(auth_cfg["header"]), "value": material}
        elif material:
            managed_auth = {"header": "Authorization",
                            "value": f"{auth_cfg.get('scheme', 'Bearer')} {material}"}
        if auth_cfg.get("query_param") and material:
            sep = "&" if "?" in target else "?"
            target = f"{target}{sep}{auth_cfg['query_param']}={material}"

    key = idempotency_key or make_idempotency_key(tenant, str(connection.id), operation or "", method, target)
    dup_stmt = select(IntegrationExecution).where(
        IntegrationExecution.tenant == tenant,
        IntegrationExecution.idempotency_key == key,
    )
    dup = (await db.execute(dup_stmt)).scalar_one_or_none()
    if dup is not None:
        return {**_serialize_execution(dup), "deduplicated": True}

    started = time.monotonic()
    status, error, attempts, response_bytes = "SUCCESS", "", 1, 0
    try:
        result = await outbound(
            tenant=tenant, method=method, url=target, headers=headers, body=body,
            timeout=timeout, max_attempts=3,
            rate_limit_key=f"integrations:{tenant}:connection:{connection.id}",
            rate_limit_max=100, actor=actor, managed_auth=managed_auth,
        )
        attempts = result["attempts"]
        response_bytes = result["bytes"]
        if result["status_code"] >= 400:
            status = "FAILED"
            error = f"http_{result['status_code']}"
    except ValidationError:
        raise
    except Exception as exc:
        status = "FAILED"
        error = f"{type(exc).__name__}"
    latency_ms = int((time.monotonic() - started) * 1000)

    row = IntegrationExecution(
        id=uuid.uuid4(), tenant=tenant, connection_id=connection.id,
        operation=operation or "", method=method, endpoint_ref=target[:1024],
        status=status, attempts=attempts, latency_ms=latency_ms,
        request_bytes=len(body or b""), response_bytes=response_bytes,
        idempotency_key=key, error=error[:500], metadata_={},
    )
    try:
        async with db.begin_nested():
            db.add(row)
            await db.flush()
    except IntegrityError:
        existing = (await db.execute(dup_stmt)).scalar_one_or_none()
        if existing is None:
            raise
        return {**_serialize_execution(existing), "deduplicated": True}
    await record_connection_result(db, tenant, connection.id, success=(status == "SUCCESS"))
    db.add(IntegrationAuditLog(
        tenant=tenant, actor=actor or "", action="execution.run",
        resource_type="connection", resource_id=str(connection.id),
        details={"operation": operation, "method": method, "status": status}, status="SUCCESS",
    ))
    await db.flush()
    return _serialize_execution(row)


async def _credential_auth_config(db: AsyncSession, tenant: str, credential_id) -> dict:
    from app.integrations.governed_models import IntegrationCredential
    stmt = select(IntegrationCredential).where(
        IntegrationCredential.id == _as_uuid(credential_id),
        IntegrationCredential.tenant == tenant,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None or not row.metadata_:
        return {}
    auth = row.metadata_.get("auth")
    return auth if isinstance(auth, dict) else {}


async def process_pending_deliveries(db: AsyncSession, tenant: str, *, limit: int = 10,
                                     worker_id: Optional[str] = None, payloads: Optional[dict] = None) -> list[dict]:
    """Deliver due webhook rows. Payloads keyed by delivery_id (scheduler-owned)."""
    from app.integrations.webhooks import deliver_attempt

    worker_id = worker_id or _worker_id()
    if not await acquire_lease(tenant, "webhook-deliveries", worker_id, ttl_seconds=120):
        return [{"status": "skipped", "reason": "lease held by another worker"}]
    try:
        now = _utcnow()
        stmt = select(IntegrationWebhookDelivery).where(
            IntegrationWebhookDelivery.tenant == tenant,
            IntegrationWebhookDelivery.status.in_(("PENDING", "RETRYING")),
            ((IntegrationWebhookDelivery.next_retry_at.is_(None))
             | (IntegrationWebhookDelivery.next_retry_at <= now)),
        ).limit(min(max(int(limit or 10), 1), 50))
        rows = (await db.execute(stmt)).scalars().all()
        results: list[dict] = []
        for row in rows:
            payload = (payloads or {}).get(row.delivery_id, {})
            try:
                results.append(await deliver_attempt(db, tenant, row.delivery_id, payload))
            except Exception as exc:
                logger.warning("delivery %s failed: %s", row.delivery_id, exc)
                results.append({"delivery_id": row.delivery_id, "status": "error",
                                "error": f"{type(exc).__name__}"})
        return results
    finally:
        await release_lease(tenant, "webhook-deliveries", worker_id)


async def run_health_check(db: AsyncSession, tenant: str, integration_id, *,
                           connection_id=None, worker_id: Optional[str] = None, actor: str = "") -> dict:
    from app.integrations.governed_models import Integration
    from app.integrations.outbound import execute as outbound

    worker_id = worker_id or _worker_id()
    stmt = select(Integration).where(Integration.id == _as_uuid(integration_id),
                                    Integration.tenant == tenant)
    integration = (await db.execute(stmt)).scalar_one_or_none()
    if integration is None:
        raise ValidationError("integration not found")

    target = None
    if connection_id:
        conn_stmt = select(IntegrationConnection).where(
            IntegrationConnection.id == _as_uuid(connection_id),
            IntegrationConnection.tenant == tenant,
        )
        conn = (await db.execute(conn_stmt)).scalar_one_or_none()
        if conn and conn.endpoint_ref:
            target = conn.endpoint_ref
    if not target:
        config = integration.config or {}
        target = config.get("health_url") or config.get("base_url") or ""

    status, latency_ms, details = "UNKNOWN", 0, {}
    if target:
        try:
            result = await outbound(tenant=tenant, method="HEAD", url=target, timeout=10.0,
                                    max_attempts=1,
                                    rate_limit_key=f"integrations:{tenant}:health",
                                    rate_limit_max=60, actor=actor)
            latency_ms = result["latency_ms"]
            code = result["status_code"]
            status = "HEALTHY" if code < 400 else ("DEGRADED" if code < 500 else "UNHEALTHY")
            details = {"status_code": code}
        except Exception as exc:
            status = "UNHEALTHY"
            details = {"error": f"{type(exc).__name__}"}
    else:
        details = {"note": "no health endpoint configured"}

    row = IntegrationHealthCheck(
        tenant=tenant, integration_id=integration.id,
        connection_id=_as_uuid(connection_id) if connection_id else None,
        status=status, latency_ms=latency_ms, checked_at=_utcnow(),
        details=sanitize_details(details), metadata_={},
    )
    db.add(row)
    integration.health = status
    await db.flush()
    try:
        from app.integrations.common import emit_event
        await emit_event("integration_health_changed",
                         {"integration_id": str(integration.id), "health": status}, tenant)
    except Exception:
        pass
    return {
        "integration_id": str(integration.id), "status": status,
        "latency_ms": latency_ms, "details": details,
        "checked_at": row.checked_at.isoformat() if row.checked_at else None,
    }


def sanitize_details(details: dict) -> dict:
    from app.integrations.common import sanitize_metadata
    return sanitize_metadata(details)
