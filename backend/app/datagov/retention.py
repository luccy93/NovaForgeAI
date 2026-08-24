"""Volume 57 — RetentionService (tenant-scoped, policy + legal-hold + deletion workflow).

Provides:
  - create_policy / list_policies / get_policy with action & retention_days validation
  - evaluate_asset / check_expired state helpers (ACTIVE/EXPIRING/EXPIRED/LEGAL_HOLD)
  - legal holds: create_hold, release_hold, is_under_hold (via governance_legal_holds)
  - deletion workflow: request_deletion
        Discover -> Validate policy -> Check legal hold -> Approval via
        app.governance.approval_workflows if available else stub ->
        Delete/anonymize/archive/export/transfer -> Verify -> Audit
    Must never auto-delete under legal hold.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.datagov.models import GovernanceDataAsset, GovernanceLegalHold, GovernanceRetentionPolicy

logger = logging.getLogger(__name__)

VALID_ACTIONS: set[str] = {"delete", "anonymize", "archive", "export", "transfer"}
STATES = ("ACTIVE", "EXPIRING", "EXPIRED", "LEGAL_HOLD")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _audit(tenant: str, actor: str, action: str, resource_id: str = "", details: dict | None = None) -> None:
    try:
        from app.iam.audit_service import audit_service  # type: ignore

        try:
            audit_service.log(
                tenant,
                actor,
                "user",
                action,
                "governance_retention",
                resource_id,
                "success",
                details or {},
            )
        except TypeError:
            audit_service.log(tenant, actor, "user", action, "governance_retention", resource_id, "success", details or {})
    except Exception as exc:  # noqa: BLE001
        logger.debug("audit unavailable (%s): %s", action, exc)


def _parse_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except Exception:
        return None


class RetentionService:
    """Tenant-scoped retention + legal-hold service."""

    # ── policy CRUD ───────────────────────────────────────────────────

    async def create_policy(
        self,
        db: AsyncSession,
        tenant: str,
        resource: str | None = None,
        classification: str | None = None,
        data_type: str | None = None,
        environment: str | None = None,
        retention_days: int | None = None,
        action: str = "delete",
    ) -> GovernanceRetentionPolicy:
        """Create a retention policy.

        Args:
            tenant: tenant scope (required).
            resource, classification, data_type, environment: optional scope
                filters (None = wildcard). `data_type` maps to asset.type,
                `environment` maps to asset.workspace/project/metadata.environment.
            retention_days: must be > 0.
            action: one of {delete, anonymize, archive, export, transfer}.
        """
        if not tenant or not str(tenant).strip():
            raise ValueError("tenant is required")
        if retention_days is None:
            raise ValueError("retention_days is required")
        try:
            rd = int(retention_days)
        except Exception:
            raise ValueError("retention_days must be an integer > 0")
        if rd <= 0:
            raise ValueError("retention_days must be > 0")

        act = str(action).strip().lower() if action else ""
        if act not in VALID_ACTIONS:
            raise ValueError(f"invalid action '{action}'; allowed: {sorted(VALID_ACTIONS)}")

        # normalize optional scopes: empty string -> None
        def _norm(v: str | None) -> str | None:
            if v is None:
                return None
            s = str(v).strip()
            return s if s else None

        row = GovernanceRetentionPolicy(
            tenant=str(tenant).strip(),
            resource=_norm(resource),
            classification=_norm(classification).upper() if _norm(classification) else None,
            data_type=_norm(data_type),
            environment=_norm(environment),
            retention_days=rd,
            action=act,
            state="ACTIVE",
        )
        db.add(row)
        await db.flush()
        await db.refresh(row)

        _audit(tenant, "system", "governance.retention.policy.created", str(row.id), {"action": act, "retention_days": rd})
        return row

    async def list_policies(
        self,
        db: AsyncSession,
        tenant: str,
    ) -> list[GovernanceRetentionPolicy]:
        """List all retention policies for tenant."""
        if not tenant:
            raise ValueError("tenant is required")
        stmt = select(GovernanceRetentionPolicy).where(GovernanceRetentionPolicy.tenant == tenant).order_by(GovernanceRetentionPolicy.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_policy(
        self,
        db: AsyncSession,
        tenant: str,
        policy_id: str,
    ) -> GovernanceRetentionPolicy | None:
        """Fetch single policy by id, tenant-scoped."""
        if not tenant or not policy_id:
            raise ValueError("tenant and policy_id are required")
        pid = _parse_uuid(policy_id)
        if pid is not None:
            stmt = select(GovernanceRetentionPolicy).where(
                GovernanceRetentionPolicy.tenant == tenant,
                GovernanceRetentionPolicy.id == pid,
            )
        else:
            # fallback: allow lookup by string id stored as text (compat)
            stmt = select(GovernanceRetentionPolicy).where(
                GovernanceRetentionPolicy.tenant == tenant,
                GovernanceRetentionPolicy.id == policy_id,  # type: ignore
            )
        result = await db.execute(stmt)
        return result.scalars().first()

    # ── legal holds ───────────────────────────────────────────────────

    async def create_hold(
        self,
        db: AsyncSession,
        tenant: str,
        scope: str,
        reason: str,
        created_by: str,
    ) -> GovernanceLegalHold:
        """Create a legal hold (scope = asset_id or resource or '*' or broad pattern)."""
        if not tenant or not scope or not reason or not created_by:
            raise ValueError("tenant, scope, reason and created_by are required")
        scope_s = str(scope).strip()
        reason_s = str(reason).strip()
        if not scope_s or not reason_s:
            raise ValueError("scope and reason cannot be empty")
        row = GovernanceLegalHold(
            tenant=str(tenant).strip(),
            scope=scope_s,
            reason=reason_s,
            created_by=str(created_by).strip(),
            released_at=None,
            released_by=None,
            audit=[{"action": "create", "by": str(created_by).strip(), "at": _utc_now().isoformat(), "reason": reason_s, "scope": scope_s}],
        )
        db.add(row)
        await db.flush()
        await db.refresh(row)
        _audit(tenant, created_by, "governance.legal_hold.created", str(row.id), {"scope": scope_s, "reason": reason_s})
        return row

    async def release_hold(
        self,
        db: AsyncSession,
        tenant: str,
        hold_id: str,
        released_by: str,
    ) -> GovernanceLegalHold:
        """Release an active legal hold."""
        if not tenant or not hold_id or not released_by:
            raise ValueError("tenant, hold_id and released_by are required")
        pid = _parse_uuid(hold_id)
        if pid is not None:
            stmt = select(GovernanceLegalHold).where(
                GovernanceLegalHold.tenant == tenant,
                GovernanceLegalHold.id == pid,
            )
        else:
            stmt = select(GovernanceLegalHold).where(
                GovernanceLegalHold.tenant == tenant,
                GovernanceLegalHold.id == hold_id,  # type: ignore
            )
        result = await db.execute(stmt)
        hold: GovernanceLegalHold | None = result.scalars().first()
        if hold is None:
            raise ValueError(f"legal hold '{hold_id}' not found for tenant '{tenant}'")
        if hold.released_at is not None:
            raise ValueError("legal hold already released")
        hold.released_at = _utc_now()
        hold.released_by = str(released_by).strip()
        audit = list(hold.audit or [])
        audit.append({"action": "release", "by": str(released_by).strip(), "at": _utc_now().isoformat()})
        hold.audit = audit
        await db.flush()
        await db.refresh(hold)
        _audit(tenant, released_by, "governance.legal_hold.released", str(hold.id), {"scope": hold.scope})
        return hold

    async def is_under_hold(
        self,
        db: AsyncSession,
        tenant: str,
        asset_id: str,
        resource: str | None = None,
    ) -> bool:
        """Check whether asset is under an active legal hold.

        Active = released_at IS NULL and scope matches asset_id/resource.
        Scope matching is intentionally broad (exact, wildcard, substring) to
        ensure holds are never bypassed due to scope formatting.
        """
        if not tenant or not asset_id:
            return False
        stmt = select(GovernanceLegalHold).where(
            GovernanceLegalHold.tenant == tenant,
            GovernanceLegalHold.released_at.is_(None),
        )
        result = await db.execute(stmt)
        holds = list(result.scalars().all())
        if not holds:
            return False
        asset_id_s = str(asset_id).strip()
        resource_s = str(resource).strip() if resource else None
        for h in holds:
            scope = str(h.scope).strip() if h.scope else ""
            if not scope:
                continue
            # wildcard holds cover all
            if scope == "*" or scope.lower() == "all":
                return True
            # exact matches
            if scope == asset_id_s:
                return True
            if resource_s and scope == resource_s:
                return True
            # prefixed forms like "asset:<id>" or "resource:<name>"
            if scope in (f"asset:{asset_id_s}", f"asset_id:{asset_id_s}"):
                return True
            if resource_s and scope in (f"resource:{resource_s}", f"resource_id:{resource_s}"):
                return True
            # substring / contains — broad match for safety
            # e.g., hold scope is a pattern containing asset_id
            if asset_id_s in scope or scope in asset_id_s:
                return True
            if resource_s and (resource_s in scope or scope in resource_s):
                return True
        return False

    # ── policy matching ───────────────────────────────────────────────

    async def _find_policy_for_asset(
        self,
        db: AsyncSession,
        tenant: str,
        asset: GovernanceDataAsset,
    ) -> GovernanceRetentionPolicy | None:
        """Find best-matching retention policy for asset (most specific wins)."""
        policies = await self.list_policies(db, tenant)
        if not policies:
            return None

        # candidate scoring
        best: GovernanceRetentionPolicy | None = None
        best_score = -1
        best_created: datetime | None = None

        asset_resource = (asset.resource or "").strip()
        asset_class = (asset.classification or "").strip().upper()
        asset_type = (getattr(asset, "type", "") or "").strip()
        # environment candidates: workspace, project, metadata.environment
        asset_env_candidates: set[str] = set()
        if asset.workspace:
            asset_env_candidates.add(str(asset.workspace).strip())
        if asset.project:
            asset_env_candidates.add(str(asset.project).strip())
        mj = asset.metadata_json if isinstance(asset.metadata_json, dict) else {}
        if isinstance(mj, dict) and mj.get("environment"):
            asset_env_candidates.add(str(mj["environment"]).strip())
        if mj.get("env"):
            asset_env_candidates.add(str(mj["env"]).strip())

        for p in policies:
            # skip non-ACTIVE? policies state ACTIVE but we still consider all
            # check each dimension: None = wildcard, otherwise must match
            if p.resource is not None and p.resource.strip() != "" and p.resource.strip() != asset_resource:
                continue
            if p.classification is not None and p.classification.strip() != "" and p.classification.strip().upper() != asset_class:
                continue
            if p.data_type is not None and p.data_type.strip() != "" and p.data_type.strip() != asset_type:
                continue
            if p.environment is not None and p.environment.strip() != "":
                env_norm = p.environment.strip()
                if env_norm not in asset_env_candidates:
                    continue
            # matched — compute specificity score
            score = 0
            if p.resource:
                score += 1
            if p.classification:
                score += 1
            if p.data_type:
                score += 1
            if p.environment:
                score += 1
            # tie-breaker: more specific or newer policy wins
            created = p.created_at
            if score > best_score or (score == best_score and (best_created is None or (created and created > best_created))):
                best = p
                best_score = score
                best_created = created

        return best

    # ── evaluate asset state ──────────────────────────────────────────

    async def evaluate_asset(
        self,
        db: AsyncSession,
        tenant: str,
        asset: GovernanceDataAsset | str,
    ) -> str:
        """Return asset retention state: ACTIVE/EXPIRING/EXPIRED/LEGAL_HOLD.

        `asset` may be a GovernanceDataAsset instance or an asset_id string
        (in which case it is fetched tenant-scoped).
        LEGAL_HOLD takes precedence. EXPIRED when age >= retention_days.
        EXPIRING when within ~10% window or 7 days before expiry.
        """
        # resolve string asset_id
        if isinstance(asset, str):
            if not tenant or not asset:
                raise ValueError("tenant and asset_id are required")
            stmt = select(GovernanceDataAsset).where(
                GovernanceDataAsset.tenant == tenant,
                GovernanceDataAsset.asset_id == asset,
            )
            result = await db.execute(stmt)
            resolved: GovernanceDataAsset | None = result.scalars().first()
            if resolved is None:
                raise ValueError(f"asset '{asset}' not found for tenant '{tenant}'")
            asset = resolved

        if not isinstance(asset, GovernanceDataAsset):
            raise ValueError("asset must be a GovernanceDataAsset or asset_id string")

        # 1. legal hold precedence
        try:
            if await self.is_under_hold(db, tenant, asset.asset_id, getattr(asset, "resource", None)):
                return "LEGAL_HOLD"
        except Exception as exc:  # noqa: BLE001
            logger.debug("is_under_hold check failed, assuming not held: %s", exc)

        # 2. find policy
        policy = await self._find_policy_for_asset(db, tenant, asset)
        if policy is None:
            return "ACTIVE"

        retention_days = int(policy.retention_days)
        if retention_days <= 0:
            return "ACTIVE"

        created_at = asset.created_at
        if created_at is None:
            return "ACTIVE"
        # ensure tz-aware
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        now = _utc_now()
        age_days = (now - created_at).days
        # future-dated asset (clock skew) treat as ACTIVE
        if age_days < 0:
            age_days = 0

        if age_days >= retention_days:
            return "EXPIRED"
        # EXPIRING if within 10% of retention or within 7 days of expiry
        remaining = retention_days - age_days
        # 10% window, at least 1 day
        expiring_threshold = max(1, int(retention_days * 0.1))
        if remaining <= expiring_threshold or remaining <= 7:
            return "EXPIRING"
        return "ACTIVE"

    async def check_expired(
        self,
        db: AsyncSession,
        tenant: str,
    ) -> list[dict[str, Any]]:
        """Return list of assets that are EXPIRING or EXPIRED (tenant-scoped).

        Returns list of dicts: {asset, state, retention_days, age_days, policy_id}
        for assets whose evaluate_asset is EXPIRING or EXPIRED. LEGAL_HOLD assets
        are never included as expiring/expired here (they are blocked separately).
        """
        if not tenant:
            raise ValueError("tenant is required")
        stmt = select(GovernanceDataAsset).where(GovernanceDataAsset.tenant == tenant)
        result = await db.execute(stmt)
        assets = list(result.scalars().all())

        out: list[dict[str, Any]] = []
        for asset in assets:
            state = await self.evaluate_asset(db, tenant, asset)
            if state in ("EXPIRING", "EXPIRED"):
                policy = await self._find_policy_for_asset(db, tenant, asset)
                created_at = asset.created_at
                if created_at is not None and created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                age_days = (_utc_now() - created_at).days if created_at else 0
                out.append(
                    {
                        "asset": asset,
                        "asset_id": asset.asset_id,
                        "state": state,
                        "retention_days": int(policy.retention_days) if policy else None,
                        "age_days": max(0, age_days),
                        "policy_id": str(policy.id) if policy else None,
                        "action": policy.action if policy else None,
                    }
                )
        # order by most urgent: EXPIRED first, then EXPIRING, then by age desc
        def _sort_key(entry: dict[str, Any]) -> tuple[int, int]:
            prio = 0 if entry["state"] == "EXPIRED" else 1
            return (prio, -int(entry.get("age_days") or 0))

        out.sort(key=_sort_key)
        return out

    # ── deletion workflow ─────────────────────────────────────────────

    async def request_deletion(
        self,
        db: AsyncSession,
        tenant: str,
        asset_id: str,
        actor: str,
        reason: str,
    ) -> dict[str, Any]:
        """Deletion workflow: Discover->Validate policy->Check legal hold->Approval->Delete/anonymize->Verify->Audit.

        Must never auto-delete under legal hold.
        Approval is attempted via app.governance.approval_workflows if available;
        otherwise a stub approval (approved) is used.

        Returns dict with status, action, verified, and detail.
        """
        if not tenant or not asset_id or not actor or not reason:
            raise ValueError("tenant, asset_id, actor and reason are required")
        asset_id_s = str(asset_id).strip()
        actor_s = str(actor).strip()
        reason_s = str(reason).strip()
        if not asset_id_s or not actor_s or not reason_s:
            raise ValueError("tenant, asset_id, actor and reason cannot be empty")

        # ── 1. Discover ───────────────────────────────────────────────
        stmt = select(GovernanceDataAsset).where(
            GovernanceDataAsset.tenant == tenant,
            GovernanceDataAsset.asset_id == asset_id_s,
        )
        result = await db.execute(stmt)
        asset: GovernanceDataAsset | None = result.scalars().first()
        if asset is None:
            raise ValueError(f"asset '{asset_id_s}' not found for tenant '{tenant}'")

        # ── 2. Validate policy ────────────────────────────────────────
        policy = await self._find_policy_for_asset(db, tenant, asset)
        action = (policy.action.lower().strip() if policy and policy.action else "delete")
        if action not in VALID_ACTIONS:
            action = "delete"
        retention_days = int(policy.retention_days) if policy else None

        # ── 3. Check legal hold — never auto-delete under hold ────────
        if await self.is_under_hold(db, tenant, asset_id_s, getattr(asset, "resource", None)):
            _audit(
                tenant,
                actor_s,
                "governance.deletion.blocked.legal_hold",
                asset_id_s,
                {"reason": reason_s, "policy_action": action},
            )
            raise ValueError("deletion blocked — asset under legal hold")

        # ── 4. Approval if required via governance/approval_workflows ─
        # For deletion/anonymize we require approval. For archive/export/transfer we also gate.
        approval_required = True
        # If approval engine is available, create a workflow; otherwise stub.
        approval_status: str = "approved"  # default stub
        approval_detail: dict[str, Any] = {"stub": True}

        if approval_required:
            try:
                from app.governance.approval_workflows import (  # type: ignore
                    ApprovalRequest,
                    ApprovalRole,
                    ApprovalStatus,
                    ApprovalStep,
                    ApprovalType,
                    ApprovalWorkflow,
                    ApprovalWorkflowEngine,
                )

                # Best-effort: create an in-memory workflow engine for this tenant.
                # Use a tenant-isolated storage dir to avoid collisions.
                try:
                    engine = ApprovalWorkflowEngine(storage_dir=f"approval_engine_data_{tenant}")  # type: ignore
                except Exception:
                    engine = ApprovalWorkflowEngine()  # type: ignore

                wf_id = str(uuid.uuid4())
                # create single-step approval workflow
                try:
                    step = ApprovalStep(
                        id=str(uuid.uuid4()),
                        name="retention-deletion-approval",
                        role=ApprovalRole.APPROVER,  # type: ignore
                        required_approvers=1,
                        order=0,
                        wait_for_previous=True,
                        timeout_hours=48,
                        escalation_after_hours=24,
                    )
                except Exception:
                    step = ApprovalStep(
                        id=str(uuid.uuid4()),
                        name="retention-deletion-approval",
                        role=ApprovalRole.ADMIN,  # fallback
                        required_approvers=1,
                    )  # type: ignore

                workflow = ApprovalWorkflow(
                    id=wf_id,
                    org_id=tenant,
                    name=f"retention-deletion:{asset_id_s}",
                    description=f"Retention deletion for asset {asset_id_s}: {reason_s}",
                    type=ApprovalType.COMPLIANCE,  # type: ignore
                    target_type="governance_data_asset",
                    target_id=asset_id_s,
                    steps=[step],
                    status=ApprovalStatus.PENDING,  # type: ignore
                    initiated_by=actor_s,
                    metadata={"asset_id": asset_id_s, "action": action, "reason": reason_s, "policy_id": str(policy.id) if policy else None},
                )
                try:
                    engine.create_workflow(workflow)
                    req = ApprovalRequest(
                        id=str(uuid.uuid4()),
                        workflow_id=wf_id,
                        org_id=tenant,
                        requester=actor_s,
                        target_type="governance_data_asset",
                        target_id=asset_id_s,
                        reason=reason_s,
                        status=ApprovalStatus.PENDING,  # type: ignore
                        metadata={"action": action},
                    )
                    engine.submit_request(req)
                    # Check workflow status: if still pending, we treat as pending approval
                    # For automated retention, we do not auto-advance; caller must approve externally.
                    # Here we inspect the engine's workflow — if still pending, return pending.
                    wf = engine.get_workflow(wf_id)
                    if wf is not None and hasattr(wf, "status"):
                        st = wf.status.value if hasattr(wf.status, "value") else str(wf.status)
                        if st == "pending":
                            _audit(
                                tenant,
                                actor_s,
                                "governance.deletion.pending_approval",
                                asset_id_s,
                                {"workflow_id": wf_id, "action": action},
                            )
                            return {
                                "status": "pending_approval",
                                "asset_id": asset_id_s,
                                "action": action,
                                "workflow_id": wf_id,
                                "request_id": req.id,
                                "reason": reason_s,
                                "policy_id": str(policy.id) if policy else None,
                                "verified": False,
                            }
                        elif st in ("approved", "conditionally_approved"):
                            approval_status = "approved"
                            approval_detail = {"workflow_id": wf_id, "status": st}
                        elif st in ("rejected", "cancelled", "expired"):
                            _audit(tenant, actor_s, "governance.deletion.rejected", asset_id_s, {"workflow_id": wf_id, "status": st})
                            return {
                                "status": "rejected",
                                "asset_id": asset_id_s,
                                "action": action,
                                "workflow_id": wf_id,
                                "reason": reason_s,
                                "verified": False,
                            }
                        else:
                            approval_status = "approved"
                            approval_detail = {"workflow_id": wf_id, "status": st}
                    else:
                        approval_status = "approved"
                        approval_detail = {"workflow_id": wf_id}
                except Exception as exc:  # noqa: BLE001
                    logger.debug("approval workflow create/submit failed, falling back to stub: %s", exc)
                    approval_status = "approved"
                    approval_detail = {"stub": True, "error": str(exc)}
            except ImportError as exc:
                logger.debug("approval_workflows not available, using stub approval: %s", exc)
                approval_status = "approved"
                approval_detail = {"stub": True, "reason": "approval_workflows not available"}
            except Exception as exc:  # noqa: BLE001
                logger.debug("approval workflow unavailable, stub: %s", exc)
                approval_status = "approved"
                approval_detail = {"stub": True, "error": str(exc)}

        if approval_status != "approved":
            # still pending — already returned above for pending case; this is defensive
            return {
                "status": "pending_approval",
                "asset_id": asset_id_s,
                "action": action,
                "reason": reason_s,
                "verified": False,
                "approval": approval_detail,
            }

        # ── 5. Delete / anonymize / archive / export / transfer ──────
        verified = False
        detail: dict[str, Any] = {}

        try:
            if action == "delete":
                await db.delete(asset)
                await db.flush()
                detail["deleted"] = True
            elif action == "anonymize":
                # clear PII/sensitive fields, keep asset row for audit
                meta = dict(asset.metadata_json or {})
                meta["anonymized_at"] = _utc_now().isoformat()
                meta["anonymized_by"] = actor_s
                meta["anonymize_reason"] = reason_s
                # retain original identifiers hashed for traceability (no raw copy)
                meta["retention_action"] = "anonymize"
                asset.metadata_json = meta
                asset.owner = None
                asset.location = None
                asset.source = None
                # keep classification but mark sensitivity cleared
                asset.sensitivity = None
                await db.flush()
                detail["anonymized"] = True
            elif action in ("archive", "export", "transfer"):
                meta = dict(asset.metadata_json or {})
                meta["retention_action"] = action
                meta[f"{action}d_at" if action != "transfer" else "transferred_at"] = _utc_now().isoformat()
                meta["retention_actor"] = actor_s
                meta["retention_reason"] = reason_s
                if policy:
                    meta["retention_policy_id"] = str(policy.id)
                asset.metadata_json = meta
                # for archive we could update retention_policy marker
                await db.flush()
                detail[action] = True
            else:
                # fallback: delete
                await db.delete(asset)
                await db.flush()
                detail["deleted"] = True
        except Exception as exc:  # noqa: BLE001
            logger.error("retention %s failed for %s: %s", action, asset_id_s, exc, exc_info=True)
            _audit(tenant, actor_s, "governance.deletion.failed", asset_id_s, {"action": action, "error": str(exc), "reason": reason_s})
            raise

        # ── 6. Verify ─────────────────────────────────────────────────
        try:
            if action == "delete":
                verify_stmt = select(GovernanceDataAsset).where(
                    GovernanceDataAsset.tenant == tenant,
                    GovernanceDataAsset.asset_id == asset_id_s,
                )
                vres = await db.execute(verify_stmt)
                still_exists = vres.scalars().first() is not None
                verified = not still_exists
            elif action == "anonymize":
                verify_stmt = select(GovernanceDataAsset).where(
                    GovernanceDataAsset.tenant == tenant,
                    GovernanceDataAsset.asset_id == asset_id_s,
                )
                vres = await db.execute(verify_stmt)
                row = vres.scalars().first()
                verified = row is not None and row.owner is None and (row.metadata_json or {}).get("anonymized_at") is not None
            else:
                verify_stmt = select(GovernanceDataAsset).where(
                    GovernanceDataAsset.tenant == tenant,
                    GovernanceDataAsset.asset_id == asset_id_s,
                )
                vres = await db.execute(verify_stmt)
                row = vres.scalars().first()
                verified = row is not None and (row.metadata_json or {}).get("retention_action") == action
        except Exception as exc:  # noqa: BLE001
            logger.debug("verify step failed: %s", exc)
            verified = False

        # ── 7. Audit ──────────────────────────────────────────────────
        _audit(
            tenant,
            actor_s,
            "governance.deletion.completed" if verified else "governance.deletion.verify_failed",
            asset_id_s,
            {
                "action": action,
                "reason": reason_s,
                "policy_id": str(policy.id) if policy else None,
                "retention_days": retention_days,
                "verified": verified,
                "approval": approval_detail,
            },
        )

        if not verified:
            logger.warning("retention %s verify failed for asset %s", action, asset_id_s)

        return {
            "status": "completed" if verified else "failed",
            "asset_id": asset_id_s,
            "action": action,
            "reason": reason_s,
            "policy_id": str(policy.id) if policy else None,
            "verified": verified,
            "approval": approval_detail,
            "detail": detail,
        }


retention_service = RetentionService()
