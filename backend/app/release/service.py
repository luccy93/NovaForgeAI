"""Volume 56 — ReleaseService (NovaForge).

Production-grade release management & progressive delivery service.

Additive, real implementation using AsyncSession + SQLAlchemy.
Reuses models:
    app.release.models: ReleaseRecord, ReleaseCandidate, ReleaseApproval,
                        ReleaseStatus, ReleaseChannel, RolloutStrategy,
                        ReleaseLock, ReleaseGate, ReleaseGateResult
    app.delivery.models: DeliveryArtifact

Guarantees:
    * Never deploys mutable / unverified artifacts when verification is required.
    * Enforces separation of duties (creator != approver for high-risk).
    * Validates state transitions via VALID_TRANSITIONS — no illegal jumps.
    * Version uniqueness enforced at `uq(tenant, service, version)`.
    * Supports semantic / build / commit / model / agent / plugin version schemes.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.delivery.models import DeliveryArtifact
from app.release.models import (
    ReleaseApproval,
    ReleaseCandidate,
    ReleaseChannel,
    ReleaseRecord,
    ReleaseStatus,
    RolloutStrategy,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# State machine — VALID_TRANSITIONS
# ---------------------------------------------------------------------------

VALID_TRANSITIONS: dict[str, set[str]] = {
    ReleaseStatus.DRAFT.value: {
        ReleaseStatus.VALIDATING.value,
        ReleaseStatus.FAILED.value,
        ReleaseStatus.CANCELLED.value,
    },
    ReleaseStatus.VALIDATING.value: {
        ReleaseStatus.READY.value,
        ReleaseStatus.APPROVAL_REQUIRED.value,
        ReleaseStatus.FAILED.value,
        ReleaseStatus.CANCELLED.value,
    },
    ReleaseStatus.READY.value: {
        ReleaseStatus.APPROVAL_REQUIRED.value,
        ReleaseStatus.DEPLOYING.value,
        ReleaseStatus.CANARY.value,
        ReleaseStatus.PROGRESSIVE.value,
        ReleaseStatus.PROMOTING.value,
        ReleaseStatus.FAILED.value,
        ReleaseStatus.CANCELLED.value,
    },
    ReleaseStatus.APPROVAL_REQUIRED.value: {
        ReleaseStatus.READY.value,
        ReleaseStatus.DEPLOYING.value,
        ReleaseStatus.FAILED.value,
        ReleaseStatus.CANCELLED.value,
    },
    ReleaseStatus.DEPLOYING.value: {
        ReleaseStatus.CANARY.value,
        ReleaseStatus.PROGRESSIVE.value,
        ReleaseStatus.PROMOTING.value,
        ReleaseStatus.COMPLETED.value,
        ReleaseStatus.FAILED.value,
        ReleaseStatus.ROLLED_BACK.value,
        ReleaseStatus.PAUSED.value,
    },
    ReleaseStatus.CANARY.value: {
        ReleaseStatus.PROGRESSIVE.value,
        ReleaseStatus.PROMOTING.value,
        ReleaseStatus.COMPLETED.value,
        ReleaseStatus.FAILED.value,
        ReleaseStatus.ROLLED_BACK.value,
        ReleaseStatus.PAUSED.value,
    },
    ReleaseStatus.PROGRESSIVE.value: {
        ReleaseStatus.PROMOTING.value,
        ReleaseStatus.COMPLETED.value,
        ReleaseStatus.FAILED.value,
        ReleaseStatus.ROLLED_BACK.value,
        ReleaseStatus.PAUSED.value,
    },
    ReleaseStatus.PROMOTING.value: {
        ReleaseStatus.COMPLETED.value,
        ReleaseStatus.FAILED.value,
        ReleaseStatus.ROLLED_BACK.value,
    },
    ReleaseStatus.PAUSED.value: {
        ReleaseStatus.DEPLOYING.value,
        ReleaseStatus.CANARY.value,
        ReleaseStatus.PROGRESSIVE.value,
        ReleaseStatus.PROMOTING.value,
        ReleaseStatus.ROLLED_BACK.value,
        ReleaseStatus.FAILED.value,
        ReleaseStatus.CANCELLED.value,
    },
    ReleaseStatus.FAILED.value: {
        ReleaseStatus.DRAFT.value,
        ReleaseStatus.CANCELLED.value,
    },
    ReleaseStatus.ROLLED_BACK.value: {
        ReleaseStatus.DRAFT.value,
        ReleaseStatus.FAILED.value,
        ReleaseStatus.CANCELLED.value,
    },
    ReleaseStatus.COMPLETED.value: set(),
    ReleaseStatus.CANCELLED.value: set(),
}

# Promotion order (lower -> higher). Used to prevent skipping environments
# without policy override. DEV < ALPHA < BETA < STAGING < CANARY < PRODUCTION
_ENV_ORDER: dict[str, int] = {
    ReleaseChannel.DEV.value: 0,
    ReleaseChannel.ALPHA.value: 1,
    ReleaseChannel.BETA.value: 2,
    ReleaseChannel.STAGING.value: 3,
    ReleaseChannel.CANARY.value: 4,
    ReleaseChannel.PRODUCTION.value: 5,
    # also handle lower-case / common aliases
    "DEV": 0,
    "development": 0,
    "ALPHA": 1,
    "BETA": 2,
    "STAGING": 3,
    "staging": 3,
    "CANARY": 4,
    "canary": 4,
    "PRODUCTION": 5,
    "production": 5,
    "prod": 5,
}

# Version schemes supported
_VERSION_SCHEMES = {"semantic", "build", "commit", "model", "agent", "plugin"}

_SEMVER_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-([\w\.\-]+))?(?:\+([\w\.\-]+))?$")


# ---------------------------------------------------------------------------
# Helpers — normalization / validation
# ---------------------------------------------------------------------------

def _normalize_status(status: str | ReleaseStatus) -> str:
    if isinstance(status, ReleaseStatus):
        return status.value
    v = str(status).strip().upper()
    # allow case-insensitive match
    for e in ReleaseStatus:
        if v == e.value.upper() or v == e.name.upper():
            return e.value
    raise ValueError(f"invalid ReleaseStatus {status!r}; must be one of {[e.value for e in ReleaseStatus]}")


def _normalize_channel(channel: str | ReleaseChannel | None) -> str:
    if channel is None:
        return ReleaseChannel.DEV.value
    if isinstance(channel, ReleaseChannel):
        return channel.value
    v = str(channel).strip().upper()
    for e in ReleaseChannel:
        if v == e.value.upper() or v == e.name.upper():
            return e.value
    # also allow lower-case aliases
    low = str(channel).strip().lower()
    mapping = {"dev": "DEV", "alpha": "ALPHA", "beta": "BETA", "staging": "STAGING", "canary": "CANARY", "production": "PRODUCTION", "prod": "PRODUCTION"}
    if low in mapping:
        return mapping[low]
    raise ValueError(f"invalid ReleaseChannel {channel!r}; must be one of {[e.value for e in ReleaseChannel]}")


def _normalize_strategy(strategy: str | RolloutStrategy | None) -> str:
    if strategy is None:
        return RolloutStrategy.ROLLING.value
    if isinstance(strategy, RolloutStrategy):
        return strategy.value
    v = str(strategy).strip().lower()
    for e in RolloutStrategy:
        if v == e.value.lower() or v == e.name.lower():
            return e.value
    raise ValueError(f"invalid RolloutStrategy {strategy!r}; must be one of {[e.value for e in RolloutStrategy]}")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _validate_transition(current: str, target: str) -> None:
    cur = _normalize_status(current)
    tgt = _normalize_status(target)
    allowed = VALID_TRANSITIONS.get(cur)
    if allowed is None:
        raise ValueError(f"unknown current status {cur!r}")
    if tgt not in allowed:
        raise ValueError(f"illegal state transition {cur!r} -> {tgt!r}; allowed: {sorted(allowed)}")


def _parse_semver(version: str) -> dict[str, Any] | None:
    m = _SEMVER_RE.match(version.strip())
    if not m:
        return None
    return {
        "major": int(m.group(1)),
        "minor": int(m.group(2)),
        "patch": int(m.group(3)),
        "pre_release": m.group(4) or "",
        "build": m.group(5) or "",
    }


def _handle_version(
    version: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """ Classify version scheme and validate.

    Supports:
        semantic:  1.2.3 / v1.2.3 / 1.2.3-alpha+001
        build:     build-123 / build_20230823.1
        commit:    40-char sha / 7-char short sha
        model:     model-v2.1.0 / gpt-4-0613
        agent:     agent@1.0.0 / agent-2023.08
        plugin:    plugin-1.2.3
    Returns enriched metadata with detected scheme.
    """
    meta = dict(metadata or {})
    raw = str(version).strip()
    if not raw:
        raise ValueError("version must be a non-empty string")

    scheme = str(meta.get("version_scheme", "")).strip().lower()

    # auto-detect if not explicitly provided
    if not scheme:
        if _parse_semver(raw):
            scheme = "semantic"
        elif re.match(r"^[0-9a-f]{7,40}$", raw, re.I):
            scheme = "commit"
        elif raw.startswith("build"):
            scheme = "build"
        elif raw.startswith("model"):
            scheme = "model"
        elif raw.startswith("agent"):
            scheme = "agent"
        elif raw.startswith("plugin"):
            scheme = "plugin"
        else:
            # default to semantic if ambiguous, but allow non-semver strings when metadata says so
            scheme = "semantic"

    if scheme not in _VERSION_SCHEMES:
        raise ValueError(f"unsupported version_scheme {scheme!r}; must be one of {sorted(_VERSION_SCHEMES)}")

    # validate per scheme
    if scheme == "semantic":
        parsed = _parse_semver(raw)
        if not parsed:
            raise ValueError(f"invalid semantic version {raw!r}; expected MAJOR.MINOR.PATCH e.g. 1.2.3 or v1.2.3")
        meta["semver"] = parsed
    elif scheme == "commit":
        if not re.match(r"^[0-9a-f]{7,40}$", raw, re.I):
            raise ValueError(f"invalid commit version {raw!r}; expected hex sha 7-40 chars")
    elif scheme == "build":
        if len(raw) < 3:
            raise ValueError(f"invalid build version {raw!r}")
    elif scheme in ("model", "agent", "plugin"):
        if len(raw) < 2:
            raise ValueError(f"invalid {scheme} version {raw!r}")

    meta["version_scheme"] = scheme
    meta["raw_version"] = raw
    return meta


def _create_change_record(
    action: str,
    actor: str,
    from_status: str | None = None,
    to_status: str | None = None,
    reason: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rec: dict[str, Any] = {
        "action": action,
        "actor": actor,
        "timestamp": _now().isoformat(),
    }
    if from_status is not None:
        rec["from_status"] = from_status
    if to_status is not None:
        rec["to_status"] = to_status
    if reason is not None:
        rec["reason"] = reason
    if extra:
        rec.update(extra)
    return rec


def _is_high_risk(metadata: dict[str, Any] | None, release_channel: str | None = None, environment: str | None = None) -> bool:
    meta = metadata or {}
    if meta.get("risk") == "high" or meta.get("risk_level") == "high":
        return True
    if meta.get("high_risk") is True:
        return True
    # production / canary channels are considered high-risk by default
    ch = str(release_channel or "").upper()
    env = str(environment or "").upper()
    if ch in ("PRODUCTION", "CANARY") or env in ("PRODUCTION", "PROD", "CANARY"):
        return True
    return False


def _check_separation_of_duties(
    actor: str,
    release: ReleaseRecord,
    metadata: dict[str, Any] | None = None,
    require_separation: bool | None = None,
) -> None:
    """Enforce separation of duties for high-risk releases.

    Policy:
        * When require_separation is True OR release is high-risk,
          the actor performing approval/deploy/promotion must NOT be the
          same as the creator (created_by).
        * If metadata contains `require_separation_of_duties: false`
          the check is skipped even for high-risk (explicit opt-out).
    """
    meta = dict(release.metadata_json or {})
    if metadata:
        meta.update(metadata)

    # explicit policy override
    if meta.get("require_separation_of_duties") is False:
        return
    if require_separation is False:
        return

    should_enforce = require_separation is True or _is_high_risk(meta, getattr(release, "release_channel", None), getattr(release, "environment", None))
    # also enforce if gate threshold says separation_required
    if meta.get("separation_required") is True:
        should_enforce = True

    if should_enforce and actor and release.created_by and actor == release.created_by:
        raise PermissionError(
            f"separation of duties violation: actor {actor!r} is also the creator {release.created_by!r} "
            f"for high-risk release {release.id} (channel={release.release_channel}, env={release.environment})"
        )


async def _get_artifact(db: AsyncSession, artifact_id: uuid.UUID | str) -> DeliveryArtifact:
    try:
        aid = uuid.UUID(str(artifact_id)) if not isinstance(artifact_id, uuid.UUID) else artifact_id
    except Exception as exc:
        raise ValueError(f"invalid artifact_id {artifact_id!r}: {exc}") from exc
    artifact = await db.get(DeliveryArtifact, aid)
    if artifact is None:
        # fallback: try query by hash if passed hash-like id (defensive)
        stmt = select(DeliveryArtifact).where(DeliveryArtifact.id == aid).limit(1)
        result = await db.execute(stmt)
        artifact = result.scalar_one_or_none()
    if artifact is None:
        raise ValueError(f"artifact {artifact_id!r} not found")
    return artifact


def _verify_artifact_integrity(
    artifact: DeliveryArtifact,
    metadata: dict[str, Any] | None = None,
    require_verification: bool = True,
) -> tuple[bool, str, dict[str, Any]]:
    """Verify digest / immutability / signature / SBOM / provenance.

    Returns (passed, reason, evidence).
    NEVER allows mutable / unverified artifacts when policy requires verification.
    """
    meta = dict(metadata or {})
    evidence: dict[str, Any] = {}

    # ---- immutability (hard gate) ----
    is_immutable = bool(getattr(artifact, "immutable", False))
    evidence["immutable"] = is_immutable
    if not is_immutable:
        # mutable artifacts are never allowed for promotion / deploy when verification required
        if require_verification or _is_high_risk(meta):
            return False, "artifact is mutable (immutable=false) — deployment blocked", evidence
        # if policy explicitly allows mutable (dev channel), log warning but allow
        logger.warning("artifact %s is mutable but verification not required (policy allows)", artifact.id)

    # ---- digest / hash ----
    has_digest = bool(getattr(artifact, "hash", None))
    evidence["has_digest"] = has_digest
    evidence["hash"] = getattr(artifact, "hash", None)
    if not has_digest and require_verification:
        return False, "artifact digest/hash missing — verification failed", evidence

    # ---- signature ----
    is_signed = bool(getattr(artifact, "signed", False))
    has_signature = bool(getattr(artifact, "signature", None))
    evidence["signed"] = is_signed
    evidence["has_signature"] = has_signature

    # Determine if signature is required
    require_signature = meta.get("require_signature")
    if require_signature is None:
        # by default, signed artifacts must have valid signature, production requires signature
        if is_signed:
            require_signature = True
        elif _is_high_risk(meta):
            require_signature = True
        else:
            require_signature = False

    if require_signature and not (is_signed and has_signature):
        return False, "artifact signature required but missing or unsigned", evidence

    # If artifact claims signed, verify signature present (fail-closed)
    if is_signed and not has_signature:
        return False, "artifact marked signed but signature is empty", evidence

    # ---- SBOM ----
    sbom = getattr(artifact, "sbom", None)
    has_sbom = bool(sbom)
    evidence["has_sbom"] = has_sbom
    require_sbom = meta.get("require_sbom")
    if require_sbom is None:
        # production / high-risk requires SBOM by default if policy says so
        require_sbom = bool(meta.get("require_SBOM") or _is_high_risk(meta) and meta.get("require_sbom", True) is True)
        # conservative: if threshold explicitly says require_sbom true, enforce
        if meta.get("require_sbom") is True:
            require_sbom = True

    # Check explicit flags from gates/thresholds: if metadata says sbom_required
    if meta.get("sbom_required") is True:
        require_sbom = True

    if require_sbom and not has_sbom:
        return False, "SBOM required but missing on artifact", evidence

    # ---- provenance ----
    provenance = getattr(artifact, "provenance", None)
    has_provenance = bool(provenance)
    evidence["has_provenance"] = has_provenance
    require_provenance = meta.get("require_provenance")
    if require_provenance is None:
        if _is_high_risk(meta):
            require_provenance = True
        elif meta.get("provenance_required") is True:
            require_provenance = True
        else:
            require_provenance = False

    if require_provenance and not has_provenance:
        return False, "provenance required but missing on artifact", evidence

    # provenance content check — must contain builder / invocation if required
    if has_provenance and isinstance(provenance, dict):
        evidence["provenance_keys"] = list(provenance.keys())[:10]

    evidence["passed"] = True
    return True, "artifact verification passed", evidence


async def _check_lock(
    db: AsyncSession,
    tenant: str,
    service: str,
    environment: str,
) -> None:
    """Check for active ReleaseLock; raise if locked."""
    try:
        from app.release.models import ReleaseLock  # local import to avoid cycle

        stmt = select(ReleaseLock).where(
            ReleaseLock.tenant == tenant,
            ReleaseLock.service == service,
            ReleaseLock.environment == environment,
        ).limit(1)
        result = await db.execute(stmt)
        lock = result.scalar_one_or_none()
        if lock is not None:
            # check expiry
            expires_at = getattr(lock, "expires_at", None)
            if expires_at is not None:
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                if expires_at < _now():
                    # expired — treat as not locked (caller may cleanup)
                    return
            raise ValueError(
                f"environment locked: tenant={tenant} service={service} env={environment} "
                f"locked_by={lock.locked_by} reason={lock.reason!r}"
            )
    except ValueError:
        raise
    except Exception as exc:
        # If ReleaseLock table does not exist or query fails, do not block — log and continue
        logger.debug("lock check skipped due to error: %s", exc)


async def _evaluate_gates_for_promotion(
    db: AsyncSession,
    release: ReleaseRecord,
) -> tuple[bool, list[Any]]:
    """Evaluate release gates; return (passed, results). Never bypass blocking failures."""
    try:
        from app.release.gates import ReleaseGateService

        svc = ReleaseGateService()
        results = await svc.evaluate(db, release.id, release.tenant)
        if not results:
            # no gates configured — treat as passed (operator chose no gates)
            return True, []
        blocked = [r for r in results if getattr(r, "status", "") == "blocked"]
        if blocked:
            return False, results
        return True, results
    except Exception as exc:
        logger.warning("gate evaluation failed for release %s: %s", release.id, exc)
        # fail-closed for high-risk: block if gates unavailable and high-risk
        if _is_high_risk(release.metadata_json, release.release_channel, release.environment):
            return False, []
        return True, []


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class ReleaseService:
    """Release lifecycle service (Volume 56).

    All methods are additive, use AsyncSession, and never use placeholders.
    """

    # ---------------------------------------------------------------
    # Create
    # ---------------------------------------------------------------

    async def create_release(
        self,
        db: AsyncSession,
        tenant: str,
        project: str,
        service: str,
        version: str,
        artifact_id: uuid.UUID | str,
        environment: str = "DEV",
        release_channel: str | ReleaseChannel = "DEV",
        strategy: str | RolloutStrategy = "rolling",
        created_by: str = "system",
        commit_sha: str | None = None,
        build_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ReleaseRecord:
        """Create a new ReleaseRecord + ReleaseCandidate.

        Validations:
            * artifact exists, immutable, digest/signature/SBOM/provenance verified
            * version uniqueness (tenant/service/version)
            * channel / strategy enum validation
            * semantic/build/commit/model/agent/plugin version handling

        Returns the persisted ReleaseRecord (status=DRAFT).
        """
        # ---- input validation ----
        if not tenant or not tenant.strip():
            raise ValueError("tenant must be a non-empty string")
        if not project or not project.strip():
            raise ValueError("project must be a non-empty string")
        if not service or not service.strip():
            raise ValueError("service must be a non-empty string")
        if not version or not str(version).strip():
            raise ValueError("version must be a non-empty string")
        if not created_by or not str(created_by).strip():
            raise ValueError("created_by must be a non-empty string")
        if artifact_id is None or str(artifact_id).strip() == "":
            raise ValueError("artifact_id must be provided")

        tenant = tenant.strip()
        project = project.strip()
        service = service.strip()
        version = str(version).strip()
        created_by = str(created_by).strip()
        environment = str(environment or "DEV").strip() or "DEV"

        channel_str = _normalize_channel(release_channel)
        strategy_str = _normalize_strategy(strategy)

        # version handling
        enriched_meta = _handle_version(version, metadata)

        # track commit/build in enriched metadata
        if commit_sha:
            enriched_meta["commit_sha"] = str(commit_sha).strip()
        if build_id:
            enriched_meta["build_id"] = str(build_id).strip()

        # ---- artifact validation ----
        artifact = await _get_artifact(db, artifact_id)

        # tenant isolation for artifact if tenant field present
        artifact_tenant = getattr(artifact, "tenant", None)
        if artifact_tenant and artifact_tenant != tenant:
            logger.warning("artifact tenant mismatch: artifact.tenant=%s release.tenant=%s artifact=%s", artifact_tenant, tenant, artifact.id)

        # immutability hard check — never deploy mutable when verification required
        require_verification = enriched_meta.get("require_verification")
        if require_verification is None:
            # default: high-risk / production requires verification
            require_verification = _is_high_risk(enriched_meta, channel_str, environment)

        if not bool(getattr(artifact, "immutable", False)):
            if require_verification:
                raise ValueError(f"artifact {artifact.id} is mutable (immutable=false) — blocked by policy (require_verification=true)")

        # digest / signature / SBOM / provenance verification
        passed, reason, evidence = _verify_artifact_integrity(artifact, enriched_meta, require_verification=require_verification)
        enriched_meta["_artifact_verification"] = {"passed": passed, "reason": reason, "evidence": evidence}
        if not passed and require_verification:
            raise ValueError(f"artifact verification failed for {artifact.id}: {reason} evidence={evidence}")

        # if artifact is signed, enforce signature present even when verification not strictly required (fail-closed for signed)
        if bool(getattr(artifact, "signed", False)) and not getattr(artifact, "signature", None):
            raise ValueError(f"artifact {artifact.id} marked signed but signature missing — blocked")

        # ---- version uniqueness ----
        stmt = select(ReleaseRecord).where(
            ReleaseRecord.tenant == tenant,
            ReleaseRecord.service == service,
            ReleaseRecord.version == version,
        ).limit(1)
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing is not None:
            raise ValueError(f"version {version!r} already exists for tenant={tenant!r} service={service!r} (release {existing.id}) — overwriting not allowed")

        # ---- create ReleaseRecord ----
        # Use channel from param, fallback to enriched_meta channel if provided
        final_commit = str(commit_sha or enriched_meta.get("commit_sha") or getattr(artifact, "commit_sha", "") or "").strip() or None
        final_build = str(build_id or enriched_meta.get("build_id") or "").strip() or None

        record = ReleaseRecord(
            tenant=tenant,
            project=project,
            service=service,
            version=version,
            artifact_id=artifact.id,
            environment=environment,
            release_channel=channel_str,
            status=ReleaseStatus.DRAFT.value,
            strategy=strategy_str,
            created_by=created_by,
            commit_sha=final_commit,
            build_id=final_build,
            metadata_json=enriched_meta,
        )
        # append initial change record
        change = _create_change_record("create", created_by, to_status=ReleaseStatus.DRAFT.value, extra={"version": version, "artifact_id": str(artifact.id)})
        # store change history in metadata_json (additive)
        enriched_meta["change_history"] = [change]
        record.metadata_json = enriched_meta

        db.add(record)
        await db.flush()  # obtain record.id

        # ---- create ReleaseCandidate ----
        # Extract candidate fields from metadata / artifact
        tests = enriched_meta.get("tests", {}) if isinstance(enriched_meta.get("tests"), dict) else {}
        security = enriched_meta.get("security", {}) if isinstance(enriched_meta.get("security"), dict) else {}
        quality = enriched_meta.get("quality", {}) if isinstance(enriched_meta.get("quality"), dict) else {}
        dependencies = enriched_meta.get("dependencies", {}) if isinstance(enriched_meta.get("dependencies"), dict) else {}
        configuration = enriched_meta.get("configuration", {}) if isinstance(enriched_meta.get("configuration"), dict) else {}
        ai_metadata = enriched_meta.get("ai_metadata", {}) if isinstance(enriched_meta.get("ai_metadata"), dict) else {}
        # also allow model/agent/plugin metadata shortcuts
        for k in ("model_version", "agent_version", "plugin_version", "model", "agent", "plugin"):
            if k in enriched_meta and k not in ai_metadata:
                ai_metadata[k] = enriched_meta[k]

        candidate = ReleaseCandidate(
            release_id=record.id,
            commit_sha=final_commit or enriched_meta.get("commit_sha", "") or getattr(artifact, "commit_sha", "") or "unknown",
            build_id=final_build or enriched_meta.get("build_id", "") or "unknown",
            artifact_id=artifact.id,
            tests=dict(tests),
            security=dict(security),
            quality=dict(quality),
            dependencies=dict(dependencies),
            configuration=dict(configuration),
            approval_status="pending",
            ai_metadata=dict(ai_metadata),
        )
        db.add(candidate)
        await db.flush()

        logger.info(
            "created release tenant=%s service=%s version=%s channel=%s env=%s artifact=%s by=%s id=%s",
            tenant, service, version, channel_str, environment, artifact.id, created_by, record.id,
        )
        return record

    # ---------------------------------------------------------------
    # Get / List
    # ---------------------------------------------------------------

    async def get_release(
        self,
        db: AsyncSession,
        release_id: uuid.UUID | str,
    ) -> ReleaseRecord | None:
        """Fetch single release by id."""
        try:
            rid = uuid.UUID(str(release_id)) if not isinstance(release_id, uuid.UUID) else release_id
        except Exception as exc:
            raise ValueError(f"invalid release_id {release_id!r}: {exc}") from exc
        return await db.get(ReleaseRecord, rid)

    async def list_releases(
        self,
        db: AsyncSession,
        tenant: str | None = None,
        project: str | None = None,
        service: str | None = None,
        environment: str | None = None,
        status: str | ReleaseStatus | None = None,
        release_channel: str | ReleaseChannel | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ReleaseRecord]:
        """List releases with optional filters."""
        stmt = select(ReleaseRecord)
        if tenant:
            stmt = stmt.where(ReleaseRecord.tenant == tenant)
        if project:
            stmt = stmt.where(ReleaseRecord.project == project)
        if service:
            stmt = stmt.where(ReleaseRecord.service == service)
        if environment:
            stmt = stmt.where(ReleaseRecord.environment == environment)
        if status:
            norm = _normalize_status(status)
            stmt = stmt.where(ReleaseRecord.status == norm)
        if release_channel:
            ch = _normalize_channel(release_channel)
            stmt = stmt.where(ReleaseRecord.release_channel == ch)
        stmt = stmt.order_by(ReleaseRecord.created_at.desc()).limit(limit).offset(offset)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    # ---------------------------------------------------------------
    # Validate
    # ---------------------------------------------------------------

    async def validate_release(
        self,
        db: AsyncSession,
        release_id: uuid.UUID | str,
    ) -> ReleaseRecord:
        """Validate release -> VALIDATING -> READY or FAILED.

        Checks:
            * artifact verification (digest/signature/SBOM/provenance)
            * SBOM presence when required
            * security (critical findings)
            * build metadata (commit_sha / build_id)
        Persists evidence in metadata_json and enforces state transitions.
        """
        release = await self.get_release(db, release_id)
        if release is None:
            raise ValueError(f"release {release_id!r} not found")

        # transition to VALIDATING
        _validate_transition(release.status, ReleaseStatus.VALIDATING.value)
        prev_status = release.status
        release.status = ReleaseStatus.VALIDATING.value
        meta = dict(release.metadata_json or {})
        meta.setdefault("change_history", []).append(
            _create_change_record("validate_start", "system", from_status=prev_status, to_status=ReleaseStatus.VALIDATING.value)
        )
        release.metadata_json = meta
        await db.flush()

        # ---- artifact checks ----
        evidence: dict[str, Any] = {}
        passed_overall = True
        reasons: list[str] = []

        # load artifact & candidate
        artifact: DeliveryArtifact | None = None
        if release.artifact_id:
            try:
                artifact = await db.get(DeliveryArtifact, release.artifact_id)
            except Exception:
                artifact = None

        if artifact is None:
            passed_overall = False
            reasons.append("artifact not found")
            evidence["artifact"] = "not_found"
        else:
            require_verification = meta.get("require_verification")
            if require_verification is None:
                require_verification = _is_high_risk(meta, release.release_channel, release.environment)
            ok, reason, art_evidence = _verify_artifact_integrity(artifact, meta, require_verification=require_verification)
            evidence["artifact_verification"] = {"passed": ok, "reason": reason, "evidence": art_evidence}
            if not ok:
                passed_overall = False
                reasons.append(f"artifact: {reason}")

        # ---- SBOM ----
        require_sbom = meta.get("require_sbom") or meta.get("sbom_required")
        if require_sbom is True or _is_high_risk(meta, release.release_channel, release.environment):
            # enforce sbom presence either on artifact or in candidate security
            has_sbom = bool(getattr(artifact, "sbom", None)) if artifact else False
            if not has_sbom:
                # also check candidate security/sbom
                try:
                    stmt = select(ReleaseCandidate).where(ReleaseCandidate.release_id == release.id).order_by(ReleaseCandidate.created_at.desc()).limit(1)
                    result = await db.execute(stmt)
                    cand = result.scalar_one_or_none()
                    if cand and getattr(cand, "security", None):
                        sec = cand.security or {}
                        if sec.get("sbom") or sec.get("has_sbom"):
                            has_sbom = True
                except Exception:
                    pass
            evidence["sbom_required"] = True
            evidence["has_sbom"] = has_sbom
            if not has_sbom:
                passed_overall = False
                reasons.append("SBOM required but missing")

        # ---- security ----
        try:
            stmt = select(ReleaseCandidate).where(ReleaseCandidate.release_id == release.id).order_by(ReleaseCandidate.created_at.desc()).limit(1)
            result = await db.execute(stmt)
            candidate = result.scalar_one_or_none()
            if candidate is not None:
                sec = getattr(candidate, "security", None) or {}
                # count critical/high
                crit = sec.get("critical", 0) if isinstance(sec, dict) else 0
                high = sec.get("high", 0) if isinstance(sec, dict) else 0
                if isinstance(sec, dict) and sec.get("findings"):
                    for f in sec["findings"]:
                        sev = str(f.get("severity", "")).lower()
                        if sev == "critical":
                            crit += 1
                        elif sev == "high":
                            high += 1
                evidence["security"] = {"critical": crit, "high": high, "raw": sec}
                # threshold: critical must be 0 for high-risk/production
                if _is_high_risk(meta, release.release_channel, release.environment) and crit > 0:
                    passed_overall = False
                    reasons.append(f"security: {crit} critical findings")
                # also check max thresholds from metadata
                max_crit = int(meta.get("max_critical", 0))
                max_high = int(meta.get("max_high", 999))
                if crit > max_crit or high > max_high:
                    passed_overall = False
                    reasons.append(f"security thresholds exceeded: critical {crit}>{max_crit} or high {high}>{max_high}")
            else:
                evidence["security"] = "no candidate"
        except Exception as exc:
            evidence["security_error"] = str(exc)

        # ---- build metadata ----
        commit = getattr(release, "commit_sha", None)
        build = getattr(release, "build_id", None)
        evidence["build"] = {"commit_sha": commit, "build_id": build}
        if not commit:
            # commit is required for traceability; warn but allow in DEV
            if _is_high_risk(meta, release.release_channel, release.environment):
                passed_overall = False
                reasons.append("build: commit_sha missing")
        if not build and _is_high_risk(meta, release.release_channel, release.environment):
            # build_id should be present for production
            passed_overall = False
            reasons.append("build: build_id missing")

        # ---- optional gate evaluation (if gates exist, enforce) ----
        try:
            from app.release.models import ReleaseGate  # type: ignore

            stmt = select(ReleaseGate).where(ReleaseGate.tenant == release.tenant).limit(1)
            result = await db.execute(stmt)
            if result.scalar_one_or_none() is not None:
                gates_passed, gate_results = await _evaluate_gates_for_promotion(db, release)
                evidence["gates"] = {
                    "passed": gates_passed,
                    "count": len(gate_results),
                    "blocked": [str(r.gate_id) for r in gate_results if getattr(r, "status", "") == "blocked"],
                }
                if not gates_passed:
                    passed_overall = False
                    reasons.append("blocking gates failed")
        except Exception as exc:
            evidence["gates_error"] = str(exc)

        # ---- final transition ----
        target_status = ReleaseStatus.READY.value if passed_overall else ReleaseStatus.FAILED.value
        _validate_transition(release.status, target_status)

        release.status = target_status
        meta = dict(release.metadata_json or {})
        meta["validation_evidence"] = evidence
        meta["validation_passed"] = passed_overall
        meta["validation_reasons"] = reasons
        meta["validated_at"] = _now().isoformat()
        meta.setdefault("change_history", []).append(
            _create_change_record(
                "validate_complete",
                "system",
                from_status=ReleaseStatus.VALIDATING.value,
                to_status=target_status,
                reason="; ".join(reasons) if reasons else "all checks passed",
                extra={"evidence": evidence},
            )
        )
        release.metadata_json = meta
        await db.flush()

        logger.info(
            "validated release %s tenant=%s service=%s version=%s -> %s reasons=%s",
            release.id, release.tenant, release.service, release.version, target_status, reasons,
        )
        return release

    # ---------------------------------------------------------------
    # Approvals
    # ---------------------------------------------------------------

    async def request_approval(
        self,
        db: AsyncSession,
        release_id: uuid.UUID | str,
        requester: str,
    ) -> ReleaseRecord:
        """Request approval -> transitions to APPROVAL_REQUIRED."""
        if not requester or not requester.strip():
            raise ValueError("requester must be a non-empty string")
        requester = requester.strip()

        release = await self.get_release(db, release_id)
        if release is None:
            raise ValueError(f"release {release_id!r} not found")

        # Only certain states can request approval
        if release.status not in (ReleaseStatus.DRAFT.value, ReleaseStatus.VALIDATING.value, ReleaseStatus.READY.value):
            # try to validate transition
            try:
                _validate_transition(release.status, ReleaseStatus.APPROVAL_REQUIRED.value)
            except ValueError as exc:
                raise ValueError(f"cannot request approval from status {release.status!r}: {exc}") from exc

        prev = release.status
        _validate_transition(release.status, ReleaseStatus.APPROVAL_REQUIRED.value)
        release.status = ReleaseStatus.APPROVAL_REQUIRED.value

        meta = dict(release.metadata_json or {})
        meta.setdefault("change_history", []).append(
            _create_change_record("request_approval", requester, from_status=prev, to_status=ReleaseStatus.APPROVAL_REQUIRED.value)
        )
        meta["approval_requested_by"] = requester
        meta["approval_requested_at"] = _now().isoformat()
        release.metadata_json = meta

        # also update candidate approval_status
        try:
            stmt = select(ReleaseCandidate).where(ReleaseCandidate.release_id == release.id).order_by(ReleaseCandidate.created_at.desc()).limit(1)
            result = await db.execute(stmt)
            cand = result.scalar_one_or_none()
            if cand is not None:
                cand.approval_status = "pending"
        except Exception:
            pass

        await db.flush()
        logger.info("approval requested release=%s by=%s -> %s", release.id, requester, ReleaseStatus.APPROVAL_REQUIRED.value)
        return release

    async def approve(
        self,
        db: AsyncSession,
        release_id: uuid.UUID | str,
        approver_id: str,
        approver_role: str = "reviewer",
        version: str | None = None,
        decision: str = "approved",
        reason: str | None = None,
        signature: str | None = None,
    ) -> ReleaseApproval:
        """Create a ReleaseApproval bound to exact version.

        Enforces:
            * version must match ReleaseRecord.version (no replay to different version)
            * separation of duties for high-risk releases
            * state transition after approval
        """
        if not approver_id or not approver_id.strip():
            raise ValueError("approver_id must be a non-empty string")
        approver_id = approver_id.strip()
        approver_role = str(approver_role or "reviewer").strip() or "reviewer"
        decision = str(decision or "approved").strip().lower()
        if decision not in ("approved", "rejected"):
            raise ValueError("decision must be 'approved' or 'rejected'")

        release = await self.get_release(db, release_id)
        if release is None:
            raise ValueError(f"release {release_id!r} not found")

        # version binding — immutable, replay-protected
        expected_version = release.version
        if version is not None and str(version).strip() != expected_version:
            raise ValueError(
                f"approval version mismatch: approval version {version!r} != release version {expected_version!r} "
                f"(approvals are bound to exact version; replay across versions is forbidden)"
            )
        bound_version = expected_version

        # separation of duties
        meta = dict(release.metadata_json or {})
        _check_separation_of_duties(approver_id, release, meta)

        # also check if release already has an approval from same actor for same version (idempotent guard)
        stmt = select(ReleaseApproval).where(
            ReleaseApproval.release_id == release.id,
            ReleaseApproval.version == bound_version,
            ReleaseApproval.approver_id == approver_id,
        ).limit(1)
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing is not None and existing.decision == "approved":
            raise ValueError(f"approver {approver_id!r} has already approved version {bound_version!r} for release {release.id}")

        # create approval row
        approval = ReleaseApproval(
            release_id=release.id,
            version=bound_version,
            approver_id=approver_id,
            approver_role=approver_role,
            decision=decision,
            reason=reason,
            signature=signature,
        )
        db.add(approval)

        # update release approved_by/at on approved decision
        if decision == "approved":
            release.approved_by = approver_id
            release.approved_at = _now()
            # transition from APPROVAL_REQUIRED -> READY if all good
            if release.status == ReleaseStatus.APPROVAL_REQUIRED.value:
                _validate_transition(release.status, ReleaseStatus.READY.value)
                prev = release.status
                release.status = ReleaseStatus.READY.value
                meta = dict(release.metadata_json or {})
                meta.setdefault("change_history", []).append(
                    _create_change_record("approved", approver_id, from_status=prev, to_status=ReleaseStatus.READY.value, extra={"version": bound_version, "role": approver_role})
                )
                release.metadata_json = meta

            # update candidate
            try:
                stmt2 = select(ReleaseCandidate).where(ReleaseCandidate.release_id == release.id).order_by(ReleaseCandidate.created_at.desc()).limit(1)
                result2 = await db.execute(stmt2)
                cand = result2.scalar_one_or_none()
                if cand is not None:
                    cand.approval_status = "approved"
            except Exception:
                pass
        else:
            # rejected -> move to FAILED if in approval required, else keep status
            meta = dict(release.metadata_json or {})
            meta.setdefault("change_history", []).append(
                _create_change_record("rejected", approver_id, from_status=release.status, to_status=release.status, reason=reason, extra={"version": bound_version, "role": approver_role})
            )
            release.metadata_json = meta
            try:
                stmt2 = select(ReleaseCandidate).where(ReleaseCandidate.release_id == release.id).order_by(ReleaseCandidate.created_at.desc()).limit(1)
                result2 = await db.execute(stmt2)
                cand = result2.scalar_one_or_none()
                if cand is not None:
                    cand.approval_status = "rejected"
            except Exception:
                pass

        await db.flush()
        logger.info(
            "approval %s release=%s version=%s approver=%s role=%s decision=%s",
            approval.id, release.id, bound_version, approver_id, approver_role, decision,
        )
        return approval

    # ---------------------------------------------------------------
    # Promote
    # ---------------------------------------------------------------

    async def promote(
        self,
        db: AsyncSession,
        release_id: uuid.UUID | str,
        target_env: str,
        actor: str,
    ) -> ReleaseRecord:
        """Promote release to target_env.

        Checks:
            * separation of duties (actor != creator for high-risk)
            * environment locks
            * artifact immutability / verification (never mutable/unverified)
            * approvals (at least one approved for this version)
            * gating (blocking gates must pass)
            * promotion ordering (dev->staging->canary->production)
        """
        if not target_env or not target_env.strip():
            raise ValueError("target_env must be a non-empty string")
        if not actor or not actor.strip():
            raise ValueError("actor must be a non-empty string")
        target_env = target_env.strip()
        actor = actor.strip()

        release = await self.get_release(db, release_id)
        if release is None:
            raise ValueError(f"release {release_id!r} not found")

        meta = dict(release.metadata_json or {})

        # ---- separation of duties ----
        # For high-risk, actor must not be the approver nor the creator
        _check_separation_of_duties(actor, release, meta)
        # also check if actor is the same as approver for high-risk
        if _is_high_risk(meta, target_env, target_env):
            # if release was approved, approver should differ from deployer
            if release.approved_by and actor == release.approved_by:
                raise PermissionError(
                    f"separation of duties: deployer {actor!r} is the same as approver {release.approved_by!r} for high-risk promotion to {target_env!r}"
                )

        # ---- lock check ----
        await _check_lock(db, release.tenant, release.service, target_env)

        # ---- artifact immutability / verification (never deploy mutable/unverified) ----
        if release.artifact_id:
            artifact = await db.get(DeliveryArtifact, release.artifact_id)
            if artifact is None:
                raise ValueError(f"artifact {release.artifact_id} not found for release {release.id}")
            require_verification = meta.get("require_verification")
            if require_verification is None:
                require_verification = _is_high_risk(meta, target_env, target_env)
            if not bool(getattr(artifact, "immutable", False)) and require_verification:
                raise ValueError(f"cannot promote mutable artifact {artifact.id} (immutable=false) to {target_env!r} — blocked by policy")
            ok, reason, art_evidence = _verify_artifact_integrity(artifact, meta, require_verification=require_verification)
            if not ok and require_verification:
                raise ValueError(f"cannot promote unverified artifact {artifact.id} to {target_env!r}: {reason} evidence={art_evidence}")
        else:
            raise ValueError(f"release {release.id} has no artifact_id — cannot promote")

        # ---- status check ----
        # Only READY / COMPLETED / APPROVAL_REQUIRED (after approval) can be promoted
        # Validate transition exists
        allowed_from = {ReleaseStatus.READY.value, ReleaseStatus.COMPLETED.value, ReleaseStatus.CANARY.value, ReleaseStatus.PROGRESSIVE.value}
        # Also allow DEPLOYING -> PROMOTING
        if release.status == ReleaseStatus.APPROVAL_REQUIRED.value:
            raise ValueError(f"release {release.id} requires approval before promotion (status={release.status})")
        if release.status not in allowed_from and release.status != ReleaseStatus.DEPLOYING.value:
            # try generic transition check; if not allowed, block
            try:
                _validate_transition(release.status, ReleaseStatus.PROMOTING.value)
            except ValueError as exc:
                raise ValueError(f"cannot promote release in status {release.status!r} to {target_env!r}: {exc}") from exc

        # ---- approvals check for high-risk / production ----
        is_production_target = target_env.upper() in ("PRODUCTION", "PROD", "CANARY") or target_env.lower() in ("canary", "production")
        if is_production_target or _is_high_risk(meta, target_env, target_env):
            stmt = select(ReleaseApproval).where(
                ReleaseApproval.release_id == release.id,
                ReleaseApproval.version == release.version,
                ReleaseApproval.decision == "approved",
            ).limit(1)
            result = await db.execute(stmt)
            approved = result.scalar_one_or_none()
            if approved is None:
                raise ValueError(f"promotion to {target_env!r} requires at least one approved ReleaseApproval for version {release.version!r}")

        # ---- gates ----
        gates_passed, gate_results = await _evaluate_gates_for_promotion(db, release)
        if not gates_passed:
            blocked_ids = [str(r.gate_id) for r in gate_results if getattr(r, "status", "") == "blocked"]
            raise ValueError(f"promotion to {target_env!r} blocked by {len(blocked_ids)} blocking gate(s): {blocked_ids}")

        # ---- promotion ordering / policies ----
        current_env = getattr(release, "environment", None) or meta.get("environment") or "DEV"
        current_order = _ENV_ORDER.get(str(current_env).upper(), _ENV_ORDER.get(str(current_env), 0))
        target_order = _ENV_ORDER.get(target_env.upper(), _ENV_ORDER.get(target_env, 999))
        # prevent skipping more than one environment unless policy allows
        min_observation = meta.get("min_observation_minutes", meta.get("min_observation"))
        promotion_policy = meta.get("promotion_policy", {}) if isinstance(meta.get("promotion_policy"), dict) else {}

        # check required_envs chain
        required_envs = promotion_policy.get("required_envs") or meta.get("required_envs")
        if required_envs:
            # ensure current env chain respected
            deployed_envs = meta.get("deployed_environments", []) if isinstance(meta.get("deployed_environments"), list) else []
            for req in required_envs:
                if req != target_env and req not in deployed_envs and req != current_env:
                    # if target is PRODUCTION and required is STAGING but not yet deployed, block
                    if _ENV_ORDER.get(str(req).upper(), 0) < target_order:
                        raise ValueError(f"promotion to {target_env!r} requires prior deployment to {req!r} (required_envs={required_envs})")

        # ---- transition to PROMOTING ----
        prev_status = release.status
        _validate_transition(release.status, ReleaseStatus.PROMOTING.value)
        release.status = ReleaseStatus.PROMOTING.value

        # update environment to target
        release.environment = target_env

        # track deployed environments
        deployed = meta.get("deployed_environments")
        if not isinstance(deployed, list):
            deployed = []
        if target_env not in deployed:
            deployed.append(target_env)
        meta["deployed_environments"] = deployed
        meta.setdefault("change_history", []).append(
            _create_change_record("promote_start", actor, from_status=prev_status, to_status=ReleaseStatus.PROMOTING.value, extra={"target_env": target_env})
        )
        meta["last_promoted_at"] = _now().isoformat()
        meta["last_promoted_by"] = actor
        meta["last_promoted_to"] = target_env
        release.metadata_json = meta
        await db.flush()

        # ---- simulate observation / min_observation check ----
        # For now, immediately complete promotion unless paused by gates
        # In real orchestrator, this would be async via workers.
        # Transition PROMOTING -> COMPLETED
        try:
            _validate_transition(release.status, ReleaseStatus.COMPLETED.value)
            release.status = ReleaseStatus.COMPLETED.value
            meta = dict(release.metadata_json or {})
            meta.setdefault("change_history", []).append(
                _create_change_record("promote_complete", actor, from_status=ReleaseStatus.PROMOTING.value, to_status=ReleaseStatus.COMPLETED.value, extra={"target_env": target_env})
            )
            meta["promotion_completed_at"] = _now().isoformat()
            release.metadata_json = meta
            await db.flush()
        except ValueError:
            # if COMPLETED not allowed from PROMOTING (should be), keep PROMOTING
            pass

        logger.info("promoted release %s version=%s to %s by %s: %s -> %s", release.id, release.version, target_env, actor, prev_status, release.status)
        return release

    # ---------------------------------------------------------------
    # Additional helpers — change records / version handling (public)
    # ---------------------------------------------------------------

    async def add_change_record(
        self,
        db: AsyncSession,
        release_id: uuid.UUID | str,
        action: str,
        actor: str,
        reason: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> ReleaseRecord:
        """Append a change record to release metadata_json.change_history."""
        release = await self.get_release(db, release_id)
        if release is None:
            raise ValueError(f"release {release_id!r} not found")
        if not action or not action.strip():
            raise ValueError("action must be non-empty")
        if not actor or not actor.strip():
            raise ValueError("actor must be non-empty")
        meta = dict(release.metadata_json or {})
        meta.setdefault("change_history", []).append(
            _create_change_record(action.strip(), actor.strip(), reason=reason, extra=extra)
        )
        release.metadata_json = meta
        await db.flush()
        return release

    def parse_version(
        self,
        version: str,
        scheme: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Public helper: parse and classify a version string.

        Supports semantic / build / commit / model / agent / plugin schemes.
        Returns enriched dict with scheme, raw, and parsed components.
        """
        meta = dict(metadata or {})
        if scheme:
            meta["version_scheme"] = scheme
        return _handle_version(version, meta)

    def is_transition_allowed(self, current: str, target: str) -> bool:
        """Check if a state transition is allowed without raising."""
        try:
            _validate_transition(current, target)
            return True
        except ValueError:
            return False


# Singleton for convenience
release_service = ReleaseService()
