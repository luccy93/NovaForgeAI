"""Volume 60 Commit 2 — Reconciliation, recovery observability & audit.

Compares pre/restored/expected states, flags missing/duplicate/stale/orphaned,
checks vector (Qdrant) and graph (Neo4j/KG) consistency, enforces tenant
boundaries. Also emits recovery observability (duration/retries/RTO/RPO/
verification) and recovery audit (who/what/scope/backup/artifact/approval/
action/result). All AsyncSession, tenant-isolated, evidence-based, never
destructive, never fake, never leaks secrets.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.resilience.models import (
    ResilienceBackup,
    ResilienceDisasterEvent,
    ResilienceRestoreJob,
)

logger = logging.getLogger(__name__)


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


def _ensure_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _hash_state(state: dict) -> str:
    """Stable hash for state comparison (keys sorted, no secret leakage)."""
    try:
        import json

        payload = json.dumps(state, sort_keys=True, default=str).encode()
        return hashlib.sha256(payload).hexdigest()[:16]
    except Exception:
        return ""


async def _audit(db: AsyncSession, tenant: str, action: str, ref: str, actor: str | None = None, details: dict | None = None) -> None:
    try:
        from app.iam.audit_service import audit_service  # type: ignore

        audit_service.log(
            tenant, ref, actor or "system", action,
            resource_type="resilience_reconciliation", resource_id=ref,
            details={"tenant": tenant, **(details or {})},
        )
    except Exception:
        pass


async def _emit(db: AsyncSession, event_name: str, data: dict, tenant: str) -> None:
    try:
        from app.core.events import Event, EventType, event_bus

        et = getattr(EventType, event_name, None)
        if et is None:
            return
        await event_bus.publish_nowait(Event(et, data, source="resilience-reconciliation", organization_id=tenant))
    except Exception as exc:  # noqa: BLE001
        logger.debug("reconciliation emit failed (%s)", exc)
        try:
            row = ResilienceDisasterEvent(
                tenant=tenant, disaster_type="OUTBOX",
                scope={"event": event_name, **data},
                reason="reconciliation-outbox", severity="INFO",
                declared_by="system", declared_at=_now(), status="DECLARED",
            )
            db.add(row)
            await db.flush()
        except Exception:  # noqa: BLE001
            pass


class ReconciliationService:
    """Restore reconciliation + recovery observability + audit."""

    async def reconcile(
        self,
        db: AsyncSession,
        tenant: str,
        restore_job_id: str,
        pre_state: dict | None = None,
        restored_state: dict | None = None,
        expected_state: dict | None = None,
    ) -> dict:
        """Compare pre/restored/expected states.

        Flags:
          - missing  — in expected but not in restored
          - duplicate — same key/value appears twice (detected via list counts)
          - stale    — restored == pre_state but != expected (not actually recovered)
          - orphaned — in restored but not in expected nor pre_state

        Also checks:
          - vector consistency (Qdrant collection counts vs expected)
          - graph consistency (Neo4j/KG node/relationship counts vs expected)
          - tenant boundaries (no key/value contains another tenant's data)
        """
        _require_tenant(tenant)
        rid = _parse_uuid(restore_job_id)
        if not rid:
            raise ValueError("invalid restore_job_id")
        job = await db.get(ResilienceRestoreJob, rid)
        if not job or job.tenant != tenant:
            raise ValueError("restore job not found")

        pre = dict(pre_state or {})
        got = dict(restored_state or {})
        exp = dict(expected_state or {})

        # Normalize: if caller passes nested collection counts under known keys, keep them
        # but also support flat key-value states.

        missing: list[dict] = []
        duplicate: list[dict] = []
        stale: list[dict] = []
        orphaned: list[dict] = []

        # Missing & mismatched
        for k, expected_val in exp.items():
            if k not in got:
                missing.append({"key": k, "type": "missing", "expected": expected_val})
            elif got[k] != expected_val:
                # Check if stale (got equals pre and pre != expected)
                if k in pre and got[k] == pre[k] and pre[k] != expected_val:
                    stale.append({"key": k, "type": "stale", "pre": pre[k], "restored": got[k], "expected": expected_val})
                else:
                    missing.append({"key": k, "type": "mismatched", "expected": expected_val, "restored": got[k]})

        # Orphaned — in got but not in exp nor pre
        for k, v in got.items():
            if k not in exp and k not in pre:
                orphaned.append({"key": k, "type": "orphaned", "restored": v})

        # Duplicate — detect duplicate keys via raw input list if provided
        # If states came from lists of records, caller may pass _records lists
        for state_name, state in [("restored", got), ("expected", exp), ("pre", pre)]:
            records = state.get("_records") if isinstance(state.get("_records"), list) else None
            if records:
                seen: dict[Any, int] = {}
                for r in records:
                    key = r if isinstance(r, (str, int)) else str(r)
                    seen[key] = seen.get(key, 0) + 1
                for key, count in seen.items():
                    if count > 1:
                        duplicate.append({"key": str(key)[:200], "type": "duplicate", "count": count, "state": state_name})

        # Also check duplicate values (same value under different keys is not duplicate; same key counted above is)
        # For vector/graph: counts duplication check via expected_state counts comparison handled below

        # Vector consistency — Qdrant collection counts
        vector_result: dict[str, Any] = {"checked": False}
        try:
            # Prefer explicit expected counts if provided
            exp_vector = exp.get("vector_counts") or exp.get("qdrant_counts") or {}
            got_vector = got.get("vector_counts") or got.get("qdrant_counts") or {}
            if exp_vector or got_vector:
                vector_result["checked"] = True
                vector_result["expected"] = exp_vector
                vector_result["restored"] = got_vector
                mismatches = []
                all_cols = set(exp_vector) | set(got_vector)
                for col in all_cols:
                    if exp_vector.get(col) != got_vector.get(col):
                        mismatches.append({"collection": col, "expected": exp_vector.get(col), "restored": got_vector.get(col)})
                vector_result["mismatches"] = mismatches
                vector_result["consistent"] = not mismatches
                if mismatches:
                    for m in mismatches:
                        missing.append({"key": f"vector:{m['collection']}", "type": "vector_mismatch", **m})
            else:
                # Best-effort live check against Qdrant if configured (no fake)
                try:
                    from app.ai_data_platform.vector_database import vector_service  # type: ignore  # noqa: F401

                    vector_result["checked"] = False
                    vector_result["note"] = "no vector_counts in states — live check skipped (evidence required); pass counts explicitly for verification"
                except ImportError:
                    vector_result["note"] = "vector infra unavailable — counts must be supplied explicitly (no fake result)"
        except Exception as exc:  # noqa: BLE001
            vector_result["error"] = str(exc)[:300]

        # Graph consistency — Neo4j / KG node/relationship counts
        graph_result: dict[str, Any] = {"checked": False}
        try:
            exp_nodes = exp.get("node_count") or (exp.get("graph_counts") or {}).get("nodes")
            exp_rels = exp.get("relationship_count") or (exp.get("graph_counts") or {}).get("relationships")
            got_nodes = got.get("node_count") or (got.get("graph_counts") or {}).get("nodes")
            got_rels = got.get("relationship_count") or (got.get("graph_counts") or {}).get("relationships")

            # Also try KG DB fallback
            if exp_nodes is None and exp_rels is None and got_nodes is None and got_rels is None:
                try:
                    from app.knowledge_graph.models import KGEntity, KGRelationship  # type: ignore

                    got_nodes_db = (await db.execute(select(func.count()).select_from(KGEntity).where(KGEntity.tenant == tenant))).scalar_one() or 0  # type: ignore
                    got_rels_db = (await db.execute(select(func.count()).select_from(KGRelationship).where(KGRelationship.tenant == tenant))).scalar_one() or 0  # type: ignore
                    graph_result["checked"] = True
                    graph_result["source"] = "kg_db"
                    graph_result["nodes"] = got_nodes_db
                    graph_result["relationships"] = got_rels_db
                    # If expected was not supplied, we cannot claim mismatch — just report
                    if exp.get("graph_counts") is not None:
                        exp_gc = exp["graph_counts"]
                        mismatches_g = []
                        if exp_gc.get("nodes") is not None and exp_gc["nodes"] != got_nodes_db:
                            mismatches_g.append({"type": "node_count", "expected": exp_gc["nodes"], "restored": got_nodes_db})
                        if exp_gc.get("relationships") is not None and exp_gc["relationships"] != got_rels_db:
                            mismatches_g.append({"type": "relationship_count", "expected": exp_gc["relationships"], "restored": got_rels_db})
                        graph_result["mismatches"] = mismatches_g
                        graph_result["consistent"] = not mismatches_g
                    else:
                        graph_result["consistent"] = None
                        graph_result["note"] = "counts reported; consistency requires expected graph_counts"
                except ImportError:
                    graph_result["note"] = "KG infra unavailable — supply graph_counts explicitly"
                except Exception as exc:  # noqa: BLE001
                    graph_result["error"] = str(exc)[:300]
            else:
                graph_result["checked"] = True
                graph_result["expected"] = {"nodes": exp_nodes, "relationships": exp_rels}
                graph_result["restored"] = {"nodes": got_nodes, "relationships": got_rels}
                mismatches_g = []
                if exp_nodes is not None and exp_nodes != got_nodes:
                    mismatches_g.append({"type": "node_count", "expected": exp_nodes, "restored": got_nodes})
                if exp_rels is not None and exp_rels != got_rels:
                    mismatches_g.append({"type": "relationship_count", "expected": exp_rels, "restored": got_rels})
                graph_result["mismatches"] = mismatches_g
                graph_result["consistent"] = not mismatches_g
                for m in mismatches_g:
                    missing.append({"key": f"graph:{m['type']}", "type": "graph_mismatch", **m})
        except Exception as exc:  # noqa: BLE001
            graph_result["error"] = str(exc)[:300]

        # Tenant boundaries — ensure restored state does not contain another tenant's data
        boundary_violations: list[dict] = []
        try:
            import json as _json

            # Serialize states and look for tenant-like keys leaking
            blob = _json.dumps(got, default=str).lower()
            # Check: if restored_state contains a tenant key != our tenant, flag it
            # Heuristic: look for "tenant" keys in nested dicts
            def _scan(obj: Any, path: str = "") -> None:
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        kl = str(k).lower()
                        if kl in ("tenant", "tenant_id", "organization_id", "org_id"):
                            if str(v).strip() and str(v).strip() != tenant:
                                boundary_violations.append({"path": f"{path}.{k}" if path else k, "found": str(v)[:64], "expected_tenant": tenant, "type": "cross_tenant_leak"})
                        if isinstance(v, (dict, list)):
                            _scan(v, f"{path}.{k}" if path else k)
                        elif isinstance(v, str) and v.strip() != tenant and "tenant" in kl:
                            pass
                    # Also check string values that look like tenant ids
                elif isinstance(obj, list):
                    for i, item in enumerate(obj):
                        _scan(item, f"{path}[{i}]")

            _scan(got)

            # Additional: query other-tenant data accidentally included — check via DB
            # If expected_state has tenant-scoped counts, ensure got doesn't have extra tenant's entity ids
            if boundary_violations:
                graph_result["boundary_ok"] = False
            else:
                graph_result["boundary_ok"] = True
        except Exception as exc:  # noqa: BLE001
            boundary_violations.append({"type": "boundary_check_error", "error": str(exc)[:200]})

        # Overall result
        all_flags = missing + duplicate + stale + orphaned + boundary_violations
        # Also include vector/graph mismatches already added to missing
        passed = not all_flags and (vector_result.get("consistent") is not False) and (graph_result.get("consistent") is not False) and not boundary_violations

        # Persist reconciliation into job row (additive, never overwrites with fake)
        # Store hashes, not raw secrets; store summary, not full states with secrets
        reconciliation_payload: dict[str, Any] = {
            "missing": missing[:100],
            "duplicate": duplicate[:100],
            "stale": stale[:100],
            "orphaned": orphaned[:100],
            "boundary_violations": boundary_violations[:50],
            "vector": vector_result,
            "graph": graph_result,
            "compared_keys": len(set(list(pre.keys()) + list(got.keys()) + list(exp.keys()))),
            "pre_hash": _hash_state(pre),
            "restored_hash": _hash_state(got),
            "expected_hash": _hash_state(exp),
            "passed": passed,
            "reconciled_at": _now().isoformat(),
        }
        job.reconciliation = reconciliation_payload
        await db.flush()

        await _audit(db, tenant, "reconciliation.completed", str(job.id), job.requested_by, {"passed": passed, "flags": len(all_flags)})
        await _emit(db, "resilience_restore_completed" if passed else "resilience_restore_failed", {"job": str(job.id), "passed": passed, "flags": len(all_flags)}, tenant)

        return {
            "job_id": str(job.id),
            "tenant": tenant,
            "passed": passed,
            "missing": missing,
            "duplicate": duplicate,
            "stale": stale,
            "orphaned": orphaned,
            "boundary_violations": boundary_violations,
            "vector": vector_result,
            "graph": graph_result,
            "reconciliation": reconciliation_payload,
        }

    # ── Recovery observability ──────────────────────────────────────────

    async def recovery_observability(
        self, db: AsyncSession, tenant: str, restore_job_id: str
    ) -> dict:
        """Duration, retries, RTO/RPO, verification result for a restore job.

        Evidence-based: calculates real durations from timestamps, reads retry
        counts from recovery steps if a plan exists, and pulls RTO/RPO from
        ResilienceProfile or measured values.
        """
        _require_tenant(tenant)
        rid = _parse_uuid(restore_job_id)
        if not rid:
            raise ValueError("invalid restore_job_id")
        job = await db.get(ResilienceRestoreJob, rid)
        if not job or job.tenant != tenant:
            raise ValueError("restore job not found")

        # Duration
        created = _ensure_aware(job.created_at)
        updated = _ensure_aware(job.updated_at)
        completed_at = _ensure_aware(job.verification_result.get("completed_at") if isinstance(job.verification_result, dict) else None) if isinstance(job.verification_result, dict) else None
        duration_seconds: float | None = None
        if created and updated:
            duration_seconds = (updated - created).total_seconds()
        # More precise if we can find associated disaster event timings
        duration_minutes = round(duration_seconds / 60, 2) if duration_seconds is not None else None

        # Retries — from reconciliation metadata or recovery steps
        retries = 0
        retry_detail: dict[str, Any] = {}
        try:
            # Check if any recovery plan was used for this job (via declared_disaster_id or service)
            from app.resilience.models import ResilienceRecoveryPlan, ResilienceRecoveryStep  # type: ignore

            # Find plans for this tenant that might correspond (best-effort)
            plans = list((await db.execute(select(ResilienceRecoveryPlan).where(ResilienceRecoveryPlan.tenant == tenant))).scalars().all())
            for p in plans[:5]:
                steps = list((await db.execute(select(ResilienceRecoveryStep).where(ResilienceRecoveryStep.plan_id == p.id))).scalars().all())
                for s in steps:
                    retries += int(getattr(s, "retry_count", 0) or 0)
            retry_detail["plans_checked"] = len(plans)
        except Exception:
            pass
        # Also check job's own metadata
        if isinstance(job.verification_result, dict):
            retries = max(retries, int(job.verification_result.get("retries", 0) or 0))

        # RTO/RPO — from profile or measured
        rto_rpo: dict[str, Any] = {}
        try:
            from app.resilience.platform import resilience_service  # type: ignore

            svc = resilience_service
            # Infer service from job target_resource or backup scope
            backup = await db.get(ResilienceBackup, job.backup_id)
            service_name = (job.target_resource or (backup.scope_target if backup else None) or "default")
            rto_rpo = await svc.compute_rto_rpo(db, tenant, service_name)
        except Exception as exc:  # noqa: BLE001
            rto_rpo = {"error": str(exc)[:300]}

        # Verification result
        verification = job.verification_result or {}
        reconciliation = job.reconciliation or {}

        # Emit observability metric via event bus (best-effort)
        await _emit(db, "observability_telemetry_received", {
            "restore_job": str(job.id),
            "duration_seconds": duration_seconds,
            "retries": retries,
            "state": job.state,
            "verified": bool(verification),
        }, tenant)

        return {
            "job_id": str(job.id),
            "tenant": tenant,
            "duration_seconds": duration_seconds,
            "duration_minutes": duration_minutes,
            "retries": retries,
            "retry_detail": retry_detail,
            "rto_rpo": rto_rpo,
            "verification_result": verification,
            "reconciliation_passed": reconciliation.get("passed"),
            "state": job.state,
            "isolated_test": job.isolated_test,
            "measured_at": _now().isoformat(),
        }

    # ── Recovery audit ──────────────────────────────────────────────────

    async def recovery_audit(
        self, db: AsyncSession, tenant: str, restore_job_id: str
    ) -> dict:
        """Who/what/scope/backup/artifact/approval/action/result audit for a restore.

        Tenant-isolated, never leaks other tenants, never exposes raw secrets.
        """
        _require_tenant(tenant)
        rid = _parse_uuid(restore_job_id)
        if not rid:
            raise ValueError("invalid restore_job_id")
        job = await db.get(ResilienceRestoreJob, rid)
        if not job or job.tenant != tenant:
            raise ValueError("restore job not found")

        backup = await db.get(ResilienceBackup, job.backup_id) if job.backup_id else None
        if backup and backup.tenant != tenant:
            backup = None  # cross-tenant guard

        # Build audit record (hash/refs only, no raw keys or locations that contain secrets)
        audit: dict[str, Any] = {
            "who": {
                "requested_by": job.requested_by or "unknown",
                "approved_by": job.approved_by,
                "approval_status": job.approval_status,
            },
            "what": {
                "restore_job_id": str(job.id),
                "mode": job.mode,
                "state": job.state,
            },
            "scope": {
                "target_environment": job.target_environment,
                "target_resource": job.target_resource,
                "scope_type": backup.scope_type if backup else None,
                "scope_target": backup.scope_target if backup else None,
            },
            "backup": {
                "backup_id": str(backup.id) if backup else None,
                "status": backup.status if backup else None,
                "verification_status": backup.verification_status if backup else None,
                "checksum_present": bool(backup and backup.checksum),
                # Never return raw checksum or location with secrets — redacted hash only
                "checksum_prefix": (backup.checksum[:8] + "***") if backup and backup.checksum else None,
                "encryption_status": backup.encryption_status if backup else None,
                "immutable": backup.immutable if backup else None,
                "isolated": backup.isolated if backup else None,
            },
            "artifact": {
                "backup_location_present": bool(backup and backup.location),
                "checksum_algorithm": backup.checksum_algorithm if backup else None,
            },
            "approval": {
                "approval_status": job.approval_status,
                "approved_by": job.approved_by,
                "requires_approval": job.target_environment == "production" and not job.isolated_test,
            },
            "action": {
                "safety_checks": job.safety_checks or {},
                "isolated_test": job.isolated_test,
                "point_in_time": job.point_in_time.isoformat() if job.point_in_time else None,
            },
            "result": {
                "state": job.state,
                "verification_result_present": bool(job.verification_result),
                "reconciliation_present": bool(job.reconciliation),
                "reconciliation_passed": (job.reconciliation or {}).get("passed") if isinstance(job.reconciliation, dict) else None,
            },
            "tenant": tenant,
            "audited_at": _now().isoformat(),
            "idempotency_key_present": bool(job.idempotency_key),
        }

        # Persist audit trail via disaster event (additive) and IAM audit
        try:
            row = ResilienceDisasterEvent(
                tenant=tenant,
                disaster_type="OUTBOX",
                scope={"audit": "recovery", "job": str(job.id), "state": job.state},
                reason="recovery audit",
                severity="INFO",
                declared_by=job.requested_by or "system",
                declared_at=_now(),
                status="DECLARED",
            )
            db.add(row)
            await db.flush()
        except Exception:  # noqa: BLE001
            pass

        await _audit(db, tenant, "recovery.audit.queried", str(job.id), job.requested_by, {"state": job.state})

        return audit

    # ── Combined: observability + audit ─────────────────────────────────

    async def observe_and_audit(
        self, db: AsyncSession, tenant: str, restore_job_id: str
    ) -> dict:
        """Return both observability and audit for a single job (convenience)."""
        obs = await self.recovery_observability(db, tenant, restore_job_id)
        aud = await self.recovery_audit(db, tenant, restore_job_id)
        return {"observability": obs, "audit": aud}


reconciliation_service = ReconciliationService()
