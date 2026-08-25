"""Volume 60 Commit 2 — Chaos engineering (resilience).

Controlled, audit-traced, tenant-isolated chaos tests with production guard.
Never destructive in production without explicit policy approval (config.allow_production).
Injects via existing infrastructure: Observability health snapshots / service health,
never deletes data or overwrites production state.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.resilience.models import ResilienceChaosTest

logger = logging.getLogger(__name__)

VALID_FAILURE_TYPES = ("service", "database", "queue", "network", "ai_provider", "storage", "event_bus")
VALID_CONFIG_KEYS = ("latency", "timeout", "error_rate", "unavailable", "resource_exhaustion", "allow_production", "policy_approved")
CHAOS_STATUSES = ("PENDING", "RUNNING", "COMPLETED", "FAILED", "ABORTED")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_uuid(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except Exception:
        return None


def _require_tenant(tenant: str) -> None:
    if not tenant or not str(tenant).strip():
        raise ValueError("tenant is required")


def _is_production_scope(scope: Any) -> bool:
    """Detect production scope from string or dict."""
    if isinstance(scope, str):
        return "production" in scope.lower()
    if isinstance(scope, dict):
        env = str(scope.get("environment", "")).lower()
        if env == "production":
            return True
        raw = str(scope.get("scope", "")).lower()
        if "production" in raw:
            return True
        # also check any value contains production
        try:
            import json
            if "production" in json.dumps(scope).lower():
                return True
        except Exception:
            pass
    return False


def _normalize_scope(scope: Any) -> tuple[dict, str | None]:
    if isinstance(scope, dict):
        return scope, scope.get("scope") or scope.get("target") or None
    if isinstance(scope, str):
        return {"scope": scope}, scope
    return {"scope": str(scope)}, str(scope)


async def _emit(db: AsyncSession, event_name: str, data: dict, tenant: str) -> None:
    try:
        from app.core.events import Event, EventType, event_bus
        et = getattr(EventType, event_name, None)
        if et is None:
            # try resilience generic
            et = getattr(EventType, "incident_detected", None)
            if et is None:
                return
        await event_bus.publish_nowait(Event(et, data, source="resilience-chaos", organization_id=tenant))
    except Exception as exc:  # noqa: BLE001
        logger.debug("chaos event emit failed (%s)", exc)
        # outbox fallback via minimal disaster row if needed: reuse pattern but don't fail main flow
        try:
            from app.resilience.models import ResilienceDisasterEvent
            row = ResilienceDisasterEvent(
                tenant=tenant,
                disaster_type="OUTBOX",
                scope={"event": event_name, **data},
                reason="chaos-outbox",
                severity="INFO",
                declared_by="system",
                declared_at=_now(),
                status="DECLARED",
            )
            db.add(row)
            await db.flush()
        except Exception:  # noqa: BLE001
            pass


async def _audit(db: AsyncSession, tenant: str, action: str, ref: str, actor: str | None = None) -> None:
    """Best-effort audit via IAM if available; never blocks."""
    try:
        from app.iam.audit_service import audit_service  # type: ignore
        audit_service.log(tenant, ref, actor or "system", action, resource_type="chaos_test", resource_id=ref,
                          details={"tenant": tenant})
    except Exception:
        pass


class ChaosService:
    """Tenant-isolated chaos test lifecycle."""

    async def create_chaos_test(
        self,
        db: AsyncSession,
        tenant: str,
        name: str,
        scope: Any,
        failure_type: str,
        config: dict | None = None,
        created_by: str | None = None,
        policy_approved: bool | None = None,
        approved_by: str | None = None,
    ) -> ResilienceChaosTest:
        _require_tenant(tenant)
        if not name or not str(name).strip():
            raise ValueError("name is required")
        if failure_type not in VALID_FAILURE_TYPES:
            raise ValueError(f"invalid failure_type {failure_type}; must be one of {VALID_FAILURE_TYPES}")
        cfg = dict(config or {})
        # validate config keys are known (allow_production/policy_approved are meta)
        unknown = [k for k in cfg.keys() if k not in VALID_CONFIG_KEYS]
        if unknown:
            raise ValueError(f"invalid config keys {unknown}; allowed {VALID_CONFIG_KEYS}")
        # At least one failure characteristic should be present if not allow_production/policy only
        failure_keys = [k for k in cfg if k in ("latency", "timeout", "error_rate", "unavailable", "resource_exhaustion")]
        # allow empty config for generic unavailable test but warn; we permit it as long as failure_type is set
        # Validate production guard: scope indicates production -> require explicit policy
        is_prod = _is_production_scope(scope)
        allow_prod = bool(cfg.get("allow_production") is True)
        # policy_approved can also be passed explicitly; config.allow_production is the policy signal
        effective_approved = bool(policy_approved) or allow_prod or bool(cfg.get("policy_approved"))
        if is_prod and not effective_approved:
            raise ValueError("production chaos requires explicit policy approval (config.allow_production=true)")

        scope_dict, scope_raw = _normalize_scope(scope)
        # merge policy_approved into config for audit trail
        cfg["policy_approved"] = effective_approved
        # keep allow_production flag visible
        if allow_prod:
            cfg["allow_production"] = True

        row = ResilienceChaosTest(
            tenant=tenant,
            name=str(name).strip(),
            scope=scope_dict,
            scope_raw=scope_raw,
            failure_type=failure_type,
            config=cfg,
            status="PENDING",
            created_by=created_by,
            policy_approved=effective_approved,
            approved_by=approved_by if effective_approved else None,
        )
        db.add(row)
        await db.flush()
        await db.refresh(row)
        await _audit(db, tenant, "chaos.test.created", str(row.id), created_by)
        await _emit(db, "resilience_backup_started", {"chaos_test": str(row.id), "failure_type": failure_type}, tenant)
        return row

    async def get_chaos_test(self, db: AsyncSession, tenant: str, test_id: str) -> ResilienceChaosTest | None:
        pid = _parse_uuid(test_id)
        if not pid:
            return None
        row = await db.get(ResilienceChaosTest, pid)
        if not row or row.tenant != tenant:
            return None
        return row

    async def list_chaos_tests(self, db: AsyncSession, tenant: str, status: str | None = None, failure_type: str | None = None, limit: int = 100) -> list[ResilienceChaosTest]:
        stmt = select(ResilienceChaosTest).where(ResilienceChaosTest.tenant == tenant)
        if status:
            stmt = stmt.where(ResilienceChaosTest.status == status)
        if failure_type:
            stmt = stmt.where(ResilienceChaosTest.failure_type == failure_type)
        stmt = stmt.order_by(ResilienceChaosTest.created_at.desc()).limit(max(1, min(limit, 500)))
        res = await db.execute(stmt)
        return list(res.scalars().all())

    async def inject_failure(
        self,
        db: AsyncSession,
        tenant: str,
        test_id: str,
        target: str | None = None,
    ) -> dict:
        """Actually inject controlled failure via existing infrastructure.

        Maps failure_type to a reversible, non-destructive mutation:
        - service/database/storage -> ObservabilityHealthSnapshot UNHEALTHY + service health_status
        - queue/event_bus -> snapshot with queue_paused=true / event_bus_unavailable=true
        - network -> snapshot latency injected
        - ai_provider -> snapshot provider unavailable

        Never destructive in production without policy_approved.
        """
        _require_tenant(tenant)
        row = await self.get_chaos_test(db, tenant, test_id)
        if not row:
            raise ValueError("chaos test not found")
        # production guard at injection time as well (defense in depth)
        is_prod = _is_production_scope(row.scope) or (target and "production" in target.lower())
        if is_prod and not row.policy_approved:
            raise ValueError("injection blocked: production target requires policy approval")

        effective_target = (target or row.target or row.scope_raw or row.scope.get("scope") or row.scope.get("target") or row.name)
        effective_target = str(effective_target).strip() if effective_target else row.name

        # Record target
        row.target = effective_target
        row.injection_metadata = {**(row.injection_metadata or {}), "last_target": effective_target, "injected_at": _now().isoformat(), "failure_type": row.failure_type}
        await db.flush()

        injected: dict[str, Any] = {"test_id": str(row.id), "failure_type": row.failure_type, "target": effective_target, "config": row.config}
        try:
            from app.observability.models import ObservabilityHealthSnapshot, ObservabilityService

            # Map failure_type to health injection
            health = "UNHEALTHY"
            checks: dict[str, Any] = {"chaos_test": str(row.id), "failure_type": row.failure_type, "isolated": True, "target": effective_target}
            cfg = row.config or {}
            if row.failure_type == "service":
                checks["injected"] = "service_unhealthy"
                health = "UNHEALTHY"
            elif row.failure_type == "database":
                checks["injected"] = "database_unavailable"
                if cfg.get("unavailable"):
                    checks["database_unavailable"] = True
                health = "UNHEALTHY"
            elif row.failure_type == "queue":
                checks["injected"] = "queue_paused"
                checks["queue_paused"] = True
                checks["error_rate"] = cfg.get("error_rate", 1.0)
                health = "DEGRADED"  # queue paused is degraded, not fully unhealthy
            elif row.failure_type == "network":
                checks["injected"] = "network_latency"
                checks["latency_ms"] = cfg.get("latency", 500)
                checks["timeout"] = cfg.get("timeout", 30)
                health = "DEGRADED"
            elif row.failure_type == "ai_provider":
                checks["injected"] = "ai_provider_unavailable"
                checks["provider_unavailable"] = True
                checks["error_rate"] = cfg.get("error_rate", 1.0)
                health = "DEGRADED"
            elif row.failure_type == "storage":
                checks["injected"] = "storage_unavailable"
                checks["resource_exhaustion"] = cfg.get("resource_exhaustion", False)
                health = "UNHEALTHY"
            elif row.failure_type == "event_bus":
                checks["injected"] = "event_bus_paused"
                checks["event_bus_unavailable"] = True
                health = "DEGRADED"

            # Always create a health snapshot (existing infrastructure, reversible)
            snap = ObservabilityHealthSnapshot(
                tenant=tenant,
                resource=effective_target,
                health=health,
                checks=checks,
                timestamp=_now(),
            )
            db.add(snap)
            # Also try to set service health_status if service exists (best effort, non-destructive)
            try:
                stmt = select(ObservabilityService).where(ObservabilityService.tenant == tenant, ObservabilityService.resource == effective_target).limit(1)
                res = await db.execute(stmt)
                svc = res.scalars().first()
                if svc:
                    svc.health_status = health
                else:
                    # also try by name
                    stmt2 = select(ObservabilityService).where(ObservabilityService.tenant == tenant, ObservabilityService.name == effective_target).limit(1)
                    res2 = await db.execute(stmt2)
                    svc2 = res2.scalars().first()
                    if svc2:
                        svc2.health_status = health
            except Exception:
                pass  # snapshot is the contract; service update is opportunistic
            await db.flush()
            injected["health_snapshot"] = {"resource": effective_target, "health": health, "checks": checks}
            injected["reversible"] = True
        except ImportError:
            # Fallback: record injection intent without infra dependency
            injected["reversible"] = True
            injected["note"] = "observability models unavailable — injection recorded as metadata only (no destructive action)"
            row.injection_metadata = {**row.injection_metadata, "fallback": True}
            await db.flush()
        except Exception as exc:  # noqa: BLE001
            logger.warning("inject_failure infra error: %s", exc)
            injected["error"] = str(exc)[:300]
            # Do not throw away the test; mark injection attempt
            row.injection_metadata = {**row.injection_metadata, "injection_error": str(exc)[:500]}
            await db.flush()
            raise ValueError(f"injection failed: {exc}") from exc

        await _audit(db, tenant, "chaos.failure.injected", str(row.id), row.created_by)
        await _emit(db, "incident_detected", {"chaos_test": str(row.id), "target": effective_target, "failure_type": row.failure_type}, tenant)
        return injected

    async def run_chaos_test(
        self,
        db: AsyncSession,
        tenant: str,
        test_id: str,
        target: str | None = None,
    ) -> ResilienceChaosTest:
        _require_tenant(tenant)
        row = await self.get_chaos_test(db, tenant, test_id)
        if not row:
            raise ValueError("chaos test not found")
        if row.status == "RUNNING":
            return row  # idempotent
        if row.status in ("COMPLETED", "ABORTED"):
            raise ValueError(f"cannot run chaos test in status {row.status}")
        # production guard
        is_prod = _is_production_scope(row.scope) or (target and "production" in target.lower())
        if is_prod and not row.policy_approved:
            raise ValueError("run blocked: production chaos requires policy approval")
        # transition to running
        row.status = "RUNNING"
        row.started_at = _now()
        if target:
            row.target = target
        await db.flush()
        # inject controlled failure as part of run (reuses existing infra)
        try:
            await self.inject_failure(db, tenant, test_id, target or row.target)
        except Exception as exc:  # noqa: BLE001
            # Injection failure should fail the run closedly, no fake success
            row.status = "FAILED"
            row.results = {**(row.results or {}), "injection_error": str(exc)[:500]}
            await db.flush()
            raise
        await _audit(db, tenant, "chaos.test.running", str(row.id), row.created_by)
        await _emit(db, "incident_detected", {"chaos_test": str(row.id), "status": "RUNNING"}, tenant)
        await db.refresh(row)
        return row

    async def complete_chaos_test(
        self,
        db: AsyncSession,
        tenant: str,
        test_id: str,
        success: bool | None = None,
        results: dict | None = None,
        passed: bool | None = None,
    ) -> ResilienceChaosTest:
        """Complete a running chaos test. Results are evidence-based, never fabricated.

        `success` or `passed` indicates whether the system recovered as expected.
        If neither provided, the call fails closed (requires explicit outcome).
        On completion, a recovery health snapshot is written (HEALTHY) to make the
        injection reversible without manual intervention.
        """
        _require_tenant(tenant)
        row = await self.get_chaos_test(db, tenant, test_id)
        if not row:
            raise ValueError("chaos test not found")
        if row.status == "COMPLETED":
            return row  # idempotent
        if row.status not in ("RUNNING", "FAILED"):
            raise ValueError(f"cannot complete chaos test in status {row.status}")
        # Require explicit evidence: success must be bool, not inferred
        if success is None and passed is None:
            raise ValueError("complete_chaos_test requires explicit success/passed boolean (no fake results)")
        effective_passed = bool(success) if success is not None else bool(passed)
        if results is not None and not isinstance(results, dict):
            raise ValueError("results must be a dict")

        row.status = "COMPLETED"
        row.completed_at = _now()
        # Preserve evidence; never fabricate missing fields
        evidence = dict(results or {})
        evidence["passed"] = effective_passed
        evidence["failure_type"] = row.failure_type
        evidence["target"] = row.target
        # Merge with existing results (do not overwrite with fake data)
        row.results = {**(row.results or {}), **evidence}
        await db.flush()

        # Reversible: write HEALTHY snapshot to restore target health (no destructive residue)
        try:
            from app.observability.models import ObservabilityHealthSnapshot, ObservabilityService
            target = row.target or row.scope_raw or row.name
            if target:
                snap = ObservabilityHealthSnapshot(
                    tenant=tenant,
                    resource=str(target),
                    health="HEALTHY",
                    checks={"chaos_test": str(row.id), "recovered": True, "passed": effective_passed},
                    timestamp=_now(),
                )
                db.add(snap)
                # opportunistically restore service health
                try:
                    stmt = select(ObservabilityService).where(ObservabilityService.tenant == tenant, ObservabilityService.resource == str(target)).limit(1)
                    res = await db.execute(stmt)
                    svc = res.scalars().first()
                    if svc:
                        svc.health_status = "HEALTHY"
                except Exception:
                    pass
                await db.flush()
        except Exception:
            pass

        await _audit(db, tenant, "chaos.test.completed", str(row.id), row.created_by)
        await _emit(db, "incident_platform_resolved" if effective_passed else "incident_detected", {"chaos_test": str(row.id), "passed": effective_passed}, tenant)
        await db.refresh(row)
        return row


chaos_service = ChaosService()
