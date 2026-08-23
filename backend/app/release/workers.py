"""Volume 56 — Release Workers (8 workers).

Each worker is an async function with try/except, using real services
(ReleaseService, GateService, Orchestrator, VerificationService,
FeatureFlagService, Locks, History, Strategies). Intended for Celery/ARQ
or asyncio background execution. No placeholders — all imports are real.

Workers:
    1. release_validation_worker      — artifact/SBOM/security/build checks
    2. gate_evaluation_worker         — never bypass blocking gates
    3. deployment_orchestration_worker — progressive delivery orchestration
    4. canary_progression_worker      — expand rollout weights, observe
    5. metric_monitoring_worker       — SLO/error/latency thresholds
    6. flag_evaluation_worker         — deterministic flag eval + audit
    7. verification_worker            — smoke/health/targeted/synthetic
    8. cleanup_worker                 — locks, expired flags, stale verifications
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# 1. Release validation worker
# ---------------------------------------------------------------------------

async def release_validation_worker(
    db: AsyncSession,
    release_id: str | uuid.UUID,
) -> dict[str, Any]:
    """Validate release via ReleaseService.validate_release.

    Checks: artifact immutability/digest/signature/SBOM/provenance,
    SBOM presence when required, security thresholds, build metadata,
    and gate evaluation if gates exist.

    Returns: {"release_id": str, "status": str, "passed": bool, "reasons": list}
    """
    try:
        from app.release.service import ReleaseService

        svc = ReleaseService()
        result = await svc.validate_release(db, release_id)
        logger.info("release_validation_worker: release %s -> %s", release_id, result.status)
        meta = getattr(result, "metadata_json", {}) or {}
        return {
            "release_id": str(result.id),
            "status": result.status,
            "passed": meta.get("validation_passed", result.status == "READY"),
            "reasons": meta.get("validation_reasons", []),
            "evidence": meta.get("validation_evidence", {}),
        }
    except ValueError as exc:
        logger.warning("release_validation_worker validation failed %s: %s", release_id, exc)
        return {"release_id": str(release_id), "status": "error", "passed": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("release_validation_worker unexpected error %s: %s", release_id, exc)
        return {"release_id": str(release_id), "status": "error", "passed": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# 2. Gate evaluation worker
# ---------------------------------------------------------------------------

async def gate_evaluation_worker(
    db: AsyncSession,
    release_id: str | uuid.UUID,
    tenant: Optional[str] = None,
) -> dict[str, Any]:
    """Evaluate release gates. Never bypasses blocking failures.

    Uses ReleaseGateService.evaluate; if any gate is 'blocked', returns
    blocked=True and does not promote. Non-blocking 'failed' is logged
    but not blocking.
    """
    try:
        from app.release.gates import ReleaseGateService
        from app.release.service import ReleaseService

        # resolve tenant if not provided
        if not tenant:
            svc = ReleaseService()
            rec = await svc.get_release(db, release_id)
            tenant = getattr(rec, "tenant", None) if rec else None

        gsvc = ReleaseGateService()
        results = await gsvc.evaluate(db, release_id, tenant or "default")
        blocked = [r for r in results if getattr(r, "status", "") == "blocked"]
        failed = [r for r in results if getattr(r, "status", "") == "failed"]
        logger.info(
            "gate_evaluation_worker: release %s tenant=%s gates=%s blocked=%s failed=%s",
            release_id, tenant, len(results), len(blocked), len(failed),
        )
        return {
            "release_id": str(release_id),
            "tenant": tenant,
            "total": len(results),
            "blocked": len(blocked),
            "failed": len(failed),
            "passed": len(blocked) == 0,
            "blocked_gate_ids": [str(getattr(r, "gate_id", "")) for r in blocked],
            "results": [{"gate_id": str(r.gate_id), "status": r.status, "score": r.score} for r in results],
        }
    except Exception as exc:
        logger.exception("gate_evaluation_worker error %s: %s", release_id, exc)
        return {"release_id": str(release_id), "error": str(exc), "passed": False, "total": 0, "blocked": 0}


# ---------------------------------------------------------------------------
# 3. Deployment orchestration worker
# ---------------------------------------------------------------------------

async def deployment_orchestration_worker(
    db: AsyncSession,
    tenant: str,
    release_id: str | uuid.UUID,
    actor: str = "system",
) -> dict[str, Any]:
    """Orchestrate deployment via ReleaseOrchestrator.orchestrate.

    Full flow: validate -> v45 check -> gates -> lock -> create deployment
    + rollout -> observe canary -> verification -> promote/pause/rollback ->
    emit events per phase. Returns orchestration result dict.
    """
    try:
        from app.release.orchestrator import ReleaseOrchestrator

        orch = ReleaseOrchestrator()
        result = await orch.orchestrate(db=db, tenant=tenant, release_id=release_id, actor=actor)
        logger.info(
            "deployment_orchestration_worker: release %s tenant=%s actor=%s -> %s",
            release_id, tenant, actor, result.get("status"),
        )
        # serialize release/deployment ids for output
        out: dict[str, Any] = {
            "release_id": str(release_id),
            "tenant": tenant,
            "actor": actor,
            "status": result.get("status"),
            "reason": result.get("reason"),
        }
        if result.get("release") and hasattr(result["release"], "id"):
            out["release_status"] = result["release"].status
        if result.get("deployment") and hasattr(result["deployment"], "id"):
            out["deployment_id"] = str(result["deployment"].id)
        if result.get("rollout") and hasattr(result["rollout"], "id"):
            out["rollout_id"] = str(result["rollout"].id)
        if result.get("verification") and hasattr(result["verification"], "id"):
            out["verification_id"] = str(result["verification"].id)
            out["verification_status"] = result["verification"].status
        out["gate_results_count"] = len(result.get("gate_results") or [])
        return out
    except ValueError as exc:
        logger.warning("deployment_orchestration_worker blocked %s: %s", release_id, exc)
        return {"release_id": str(release_id), "tenant": tenant, "error": str(exc), "status": "blocked"}
    except PermissionError as exc:
        logger.warning("deployment_orchestration_worker permission %s: %s", release_id, exc)
        return {"release_id": str(release_id), "tenant": tenant, "error": str(exc), "status": "forbidden"}
    except Exception as exc:
        logger.exception("deployment_orchestration_worker unexpected %s: %s", release_id, exc)
        return {"release_id": str(release_id), "tenant": tenant, "error": str(exc), "status": "error"}


# ---------------------------------------------------------------------------
# 4. Canary progression worker
# ---------------------------------------------------------------------------

async def canary_progression_worker(
    db: AsyncSession,
    release_id: str | uuid.UUID,
    actor: str = "system",
) -> dict[str, Any]:
    """Progress canary rollout by one weight step and observe metrics.

    Resolves DeliveryRollout for the release's deployment, expands weight
    via DeploymentService.expand_rollout, checks should_rollback, and
    either rolls back, pauses, or continues. Uses real DeploymentService.
    """
    try:
        from app.release.models import ReleaseRecord
        from app.delivery.models import DeliveryDeployment, DeliveryRollout
        from app.delivery.deployment_service import DeploymentService

        rid = uuid.UUID(str(release_id)) if not isinstance(release_id, uuid.UUID) else release_id
        release = await db.get(ReleaseRecord, rid)
        if not release:
            return {"release_id": str(release_id), "error": "release not found", "status": "not_found"}

        # find latest deployment for release version
        dep_res = await db.execute(
            select(DeliveryDeployment)
            .where(DeliveryDeployment.version == release.version, DeliveryDeployment.tenant == release.tenant)
            .order_by(DeliveryDeployment.created_at.desc())
            .limit(1)
        )
        dep = dep_res.scalar_one_or_none()
        if not dep:
            return {"release_id": str(release_id), "error": "deployment not found for release", "status": "no_deployment"}

        roll_res = await db.execute(
            select(DeliveryRollout).where(DeliveryRollout.deployment_id == dep.id).limit(1)
        )
        rollout = roll_res.scalar_one_or_none()
        if not rollout:
            return {"release_id": str(release_id), "error": "rollout not found", "status": "no_rollout"}

        dep_svc = DeploymentService(db)

        # check metrics before expansion
        pre_check = await dep_svc.should_rollback(
            dep.id,
            error_rate_threshold=float(getattr(rollout, "error_rate_threshold", 0.05)),
            latency_threshold_ms=int(getattr(rollout, "latency_threshold_ms", 1000)),
        )
        if pre_check.get("should_rollback"):
            rb = await dep_svc.create_rollback(
                deployment_id=dep.id,
                reason=f"canary progression blocked by metrics: {pre_check.get('reasons')}",
                initiated_by=actor,
                automatic=True,
            )
            logger.warning("canary_progression_worker: pre-expansion rollback release=%s reasons=%s", release_id, pre_check.get("reasons"))
            return {"release_id": str(release_id), "status": "rolled_back", "reason": str(pre_check.get("reasons")), "rollback_id": str(rb.id)}

        # expand one stage
        if getattr(rollout, "status", "") in ("completed", "aborted"):
            return {"release_id": str(release_id), "status": str(rollout.status), "current_weight": getattr(rollout, "current_weight", None), "stage": getattr(rollout, "current_stage", None)}

        expanded = await dep_svc.expand_rollout(rollout.id)

        # observe after expansion
        post_check = await dep_svc.should_rollback(
            dep.id,
            error_rate_threshold=float(getattr(expanded, "error_rate_threshold", 0.05)),
            latency_threshold_ms=int(getattr(expanded, "latency_threshold_ms", 1000)),
        )
        if post_check.get("should_rollback"):
            if getattr(expanded, "auto_abort", True):
                rb2 = await dep_svc.create_rollback(
                    deployment_id=dep.id,
                    reason=f"post-expansion canary degradation: {post_check.get('reasons')}",
                    initiated_by=actor,
                    automatic=True,
                )
                logger.warning("canary_progression_worker: post-expansion rollback release=%s", release_id)
                return {"release_id": str(release_id), "status": "rolled_back", "reason": str(post_check.get("reasons")), "rollback_id": str(rb2.id), "current_weight": getattr(expanded, "current_weight", None)}
            else:
                logger.info("canary_progression_worker: paused release=%s due to canary degradation", release_id)
                return {"release_id": str(release_id), "status": "paused", "reason": str(post_check.get("reasons")), "current_weight": getattr(expanded, "current_weight", None)}

        logger.info(
            "canary_progression_worker: expanded release=%s weight=%s stage=%s",
            release_id, getattr(expanded, "current_weight", None), getattr(expanded, "current_stage", None),
        )
        return {
            "release_id": str(release_id),
            "status": getattr(expanded, "status", "running"),
            "current_weight": getattr(expanded, "current_weight", None),
            "current_stage": getattr(expanded, "current_stage", None),
            "target_weight": getattr(expanded, "target_weight", None),
        }
    except Exception as exc:
        logger.exception("canary_progression_worker error %s: %s", release_id, exc)
        return {"release_id": str(release_id), "error": str(exc), "status": "error"}


# ---------------------------------------------------------------------------
# 5. Metric monitoring worker
# ---------------------------------------------------------------------------

async def metric_monitoring_worker(
    db: AsyncSession,
    release_id: str | uuid.UUID,
) -> dict[str, Any]:
    """Monitor canary/deployment metrics for SLO breaches.

    Inspects ReleaseRecord.metadata_json metrics_snapshot / canary_metrics
    and DeliveryRollout.metrics_snapshot, evaluates SLOs via analytics
    thresholds, and triggers pause/rollback decision if needed. Never
    mutates production data directly except via DeploymentService decisions.
    """
    try:
        from app.release.models import ReleaseRecord
        from app.delivery.models import DeliveryDeployment, DeliveryRollout
        from app.delivery.deployment_service import DeploymentService

        rid = uuid.UUID(str(release_id)) if not isinstance(release_id, uuid.UUID) else release_id
        release = await db.get(ReleaseRecord, rid)
        if not release:
            return {"release_id": str(release_id), "error": "release not found"}

        meta = getattr(release, "metadata_json", {}) or {}
        metrics_snapshot: dict[str, Any] = {}
        if isinstance(meta.get("metrics_snapshot"), dict):
            metrics_snapshot.update(meta["metrics_snapshot"])
        if isinstance(meta.get("canary_metrics"), dict):
            metrics_snapshot.update(meta["canary_metrics"])

        # also merge rollout snapshot if available
        dep_res = await db.execute(
            select(DeliveryDeployment)
            .where(DeliveryDeployment.version == release.version, DeliveryDeployment.tenant == release.tenant)
            .order_by(DeliveryDeployment.created_at.desc())
            .limit(1)
        )
        dep = dep_res.scalar_one_or_none()
        rollout = None
        if dep:
            roll_res = await db.execute(select(DeliveryRollout).where(DeliveryRollout.deployment_id == dep.id).limit(1))
            rollout = roll_res.scalar_one_or_none()
            if rollout and getattr(rollout, "metrics_snapshot", None):
                try:
                    metrics_snapshot.update(dict(rollout.metrics_snapshot))
                except Exception:
                    pass

        # thresholds
        error_rate_threshold = 0.05
        latency_threshold_ms = 1000
        slo_breach_reasons: list[str] = []

        # determine thresholds from strategy config or rollout
        if rollout:
            error_rate_threshold = float(getattr(rollout, "error_rate_threshold", error_rate_threshold))
            latency_threshold_ms = int(getattr(rollout, "latency_threshold_ms", latency_threshold_ms))

        strategy_config = meta.get("release_strategy_config") or meta.get("strategy_config") or {}
        if isinstance(strategy_config, dict):
            if "error_rate_threshold" in strategy_config:
                try:
                    error_rate_threshold = float(strategy_config["error_rate_threshold"])
                except Exception:
                    pass
            if "latency_threshold_ms" in strategy_config:
                try:
                    latency_threshold_ms = int(strategy_config["latency_threshold_ms"])
                except Exception:
                    pass

        # evaluate snapshot
        error_rate = None
        latency = None
        if metrics_snapshot:
            error_rate = metrics_snapshot.get("error_rate", metrics_snapshot.get("errorRate"))
            latency = metrics_snapshot.get("latency_ms", metrics_snapshot.get("latency", metrics_snapshot.get("p95_latency_ms")))

        if error_rate is not None:
            try:
                if float(error_rate) > error_rate_threshold:
                    slo_breach_reasons.append(f"error_rate {error_rate} > threshold {error_rate_threshold}")
            except Exception:
                pass
        if latency is not None:
            try:
                if float(latency) > latency_threshold_ms:
                    slo_breach_reasons.append(f"latency {latency}ms > threshold {latency_threshold_ms}ms")
            except Exception:
                pass

        # also delegate to DeploymentService.should_rollback for authoritative check
        if dep:
            dep_svc = DeploymentService(db)
            rb_check = await dep_svc.should_rollback(dep.id, error_rate_threshold=error_rate_threshold, latency_threshold_ms=latency_threshold_ms)
            if rb_check.get("should_rollback"):
                for r in rb_check.get("reasons", []):
                    if r not in slo_breach_reasons:
                        slo_breach_reasons.append(str(r))

        breached = len(slo_breach_reasons) > 0
        logger.info(
            "metric_monitoring_worker: release %s metrics=%s breached=%s reasons=%s",
            release_id, metrics_snapshot, breached, slo_breach_reasons,
        )
        return {
            "release_id": str(release_id),
            "metrics_snapshot": metrics_snapshot,
            "error_rate_threshold": error_rate_threshold,
            "latency_threshold_ms": latency_threshold_ms,
            "breached": breached,
            "reasons": slo_breach_reasons,
            "status": "breach" if breached else "healthy",
        }
    except Exception as exc:
        logger.exception("metric_monitoring_worker error %s: %s", release_id, exc)
        return {"release_id": str(release_id), "error": str(exc), "status": "error"}


# ---------------------------------------------------------------------------
# 6. Flag evaluation worker
# ---------------------------------------------------------------------------

async def flag_evaluation_worker(
    db: AsyncSession,
    tenant: str,
    flag_key: str,
    context: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Evaluate a feature flag deterministically and audit evaluation.

    Uses FeatureFlagService.evaluate with sanitized context, consistent
    hashing, state machine, and best-effort persistence to
    FeatureFlagEvaluation.
    """
    try:
        from app.release.flags import FeatureFlagService

        svc = FeatureFlagService()
        result = await svc.evaluate(db, tenant, flag_key, context or {})
        logger.info(
            "flag_evaluation_worker: tenant=%s key=%s value=%s reason=%s bucket=%s",
            tenant, flag_key, result.get("value"), result.get("reason"), result.get("bucket"),
        )
        return {
            "tenant": tenant,
            "flag_key": flag_key,
            "value": result.get("value"),
            "reason": result.get("reason"),
            "version": result.get("version"),
            "bucket": result.get("bucket"),
            "flag_id": str(result["flag"].id) if result.get("flag") else None,
        }
    except Exception as exc:
        logger.exception("flag_evaluation_worker error tenant=%s key=%s: %s", tenant, flag_key, exc)
        # fallback to safe default on any unexpected error (service unavailable)
        return {"tenant": tenant, "flag_key": flag_key, "value": "false", "reason": "fallback_error", "error": str(exc)}


# ---------------------------------------------------------------------------
# 7. Verification worker
# ---------------------------------------------------------------------------

async def verification_worker(
    db: AsyncSession,
    release_id: str | uuid.UUID,
    verification_type: str = "smoke",
) -> dict[str, Any]:
    """Create and run a verification for release.

    Supports smoke/health/targeted/synthetic via VerificationService.
    Never mutates production data; only reads and writes verification
    result evidence.
    """
    try:
        from app.release.verifications import VerificationService

        vsvc = VerificationService()
        ver = await vsvc.create_verification(db, release_id, verification_type)
        ver = await vsvc.run_verification(db, ver.id)
        logger.info(
            "verification_worker: release %s type=%s status=%s passed=%s",
            release_id, verification_type, ver.status, ver.result.get("passed") if isinstance(ver.result, dict) else None,
        )
        return {
            "release_id": str(release_id),
            "verification_id": str(ver.id),
            "verification_type": ver.verification_type,
            "status": ver.status,
            "result": ver.result,
            "checks": ver.checks,
        }
    except ValueError as exc:
        logger.warning("verification_worker validation error %s type=%s: %s", release_id, verification_type, exc)
        return {"release_id": str(release_id), "error": str(exc), "status": "error"}
    except Exception as exc:
        logger.exception("verification_worker unexpected error %s type=%s: %s", release_id, verification_type, exc)
        return {"release_id": str(release_id), "error": str(exc), "status": "error"}


# ---------------------------------------------------------------------------
# 8. Cleanup worker
# ---------------------------------------------------------------------------

async def cleanup_worker(
    db: AsyncSession,
    tenant: Optional[str] = None,
    release_id: Optional[str | uuid.UUID] = None,
) -> dict[str, Any]:
    """Cleanup: release locks, expired flags, stale verifications.

    Steps (all best-effort, never raise):
        - release expired ReleaseLocks (expires_at < now)
        - flag expiry warnings via FeatureFlagService.check_expiry + auto-log
        - stale verifications older than 7 days in PENDING/RUNNING -> FAILED
        - if release_id provided, release its env lock
    """
    try:
        cleaned: dict[str, Any] = {"locks": 0, "flags_warnings": 0, "verifications": 0}

        # ── locks: delete expired ────────────────────────────────────────
        try:
            from app.release.models import ReleaseLock

            now = _now()
            stmt = select(ReleaseLock)
            if tenant:
                stmt = stmt.where(ReleaseLock.tenant == tenant)
            # only where expires_at is set and expired
            stmt = stmt.where(ReleaseLock.expires_at.is_not(None))
            result = await db.execute(stmt)
            locks = list(result.scalars().all())
            for lock in locks:
                exp = getattr(lock, "expires_at", None)
                if exp is None:
                    continue
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                if exp < now:
                    # optionally if specific release_id, only clean that env
                    await db.delete(lock)
                    cleaned["locks"] += 1
            if cleaned["locks"]:
                await db.flush()
                logger.info("cleanup_worker: removed %s expired locks", cleaned["locks"])
        except Exception as exc:
            logger.debug("cleanup_worker lock cleanup error: %s", exc)

        # ── specific release lock release if release_id provided ──────────
        if release_id:
            try:
                from app.release.locks import ReleaseLockService
                from app.release.models import ReleaseRecord

                rid = uuid.UUID(str(release_id)) if not isinstance(release_id, uuid.UUID) else release_id
                rec = await db.get(ReleaseRecord, rid)
                if rec:
                    ls = ReleaseLockService()
                    lock = await ls.check_lock(db, rec.tenant, rec.service, rec.environment)
                    if lock and tenant is None or (lock.tenant == tenant):
                        # only release if expired or forced; here we release if present and release is terminal
                        if getattr(rec, "status", "") in ("COMPLETED", "FAILED", "ROLLED_BACK", "CANCELLED"):
                            await ls.release_lock(db, lock.id, "cleanup_worker")
                            cleaned["locks"] += 1
                            logger.info("cleanup_worker: released lock %s for release %s", lock.id, release_id)
            except Exception as exc:
                logger.debug("cleanup_worker release-specific lock error: %s", exc)

        # ── flags: expiry warnings ────────────────────────────────────────
        try:
            from app.release.flags import FeatureFlagService

            fs = FeatureFlagService()
            warnings = await fs.check_expiry(db, tenant=tenant, warn_days=30)
            cleaned["flags_warnings"] = len(warnings)
            if warnings:
                logger.info("cleanup_worker: flag expiry warnings tenant=%s count=%s", tenant, len(warnings))
                # warnings are logged inside service; we just count
        except Exception as exc:
            logger.debug("cleanup_worker flag check error: %s", exc)

        # ── verifications: stale PENDING/RUNNING older than 7d -> FAILED ──
        try:
            from app.release.models import ReleaseVerification, VerificationStatus

            cutoff = _now() - timedelta(days=7)
            stmt = select(ReleaseVerification).where(
                ReleaseVerification.status.in_([VerificationStatus.PENDING.value, VerificationStatus.RUNNING.value]),
                ReleaseVerification.created_at < cutoff,
            )
            result = await db.execute(stmt)
            stale = list(result.scalars().all())
            for ver in stale:
                ver.status = VerificationStatus.FAILED.value
                if isinstance(ver.result, dict):
                    ver.result["cleanup_marked"] = True
                    ver.result["cleanup_reason"] = "stale verification auto-failed after 7d"
                else:
                    ver.result = {"passed": False, "reason": "stale verification auto-failed after 7d", "cleanup_marked": True}
                cleaned["verifications"] += 1
            if cleaned["verifications"]:
                await db.flush()
                logger.info("cleanup_worker: marked %s stale verifications as FAILED", cleaned["verifications"])
        except Exception as exc:
            logger.debug("cleanup_worker verification cleanup error: %s", exc)

        logger.info("cleanup_worker: tenant=%s release=%s cleaned=%s", tenant, release_id, cleaned)
        return {"tenant": tenant, "release_id": str(release_id) if release_id else None, "cleaned": cleaned, "at": _now().isoformat()}
    except Exception as exc:
        logger.exception("cleanup_worker unexpected error tenant=%s release=%s: %s", tenant, release_id, exc)
        return {"tenant": tenant, "release_id": str(release_id) if release_id else None, "error": str(exc), "cleaned": {}}
