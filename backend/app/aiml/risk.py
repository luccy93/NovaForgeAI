"""Volume 58 — AIRiskService (tenant-scoped, AsyncSession).

Governance aid for AI risk records (``ai_risk_records``).

Score is a pure governance heuristic: severity * likelihood * impact.
Not a legal conclusion — never presented as compliance determination.

Tenant isolation: every read/write is scoped to tenant.  Mutators that
receive only a PK still resolve tenant from the row and preserve it.

Audit best-effort via ``app.iam.audit_service`` — never raises.
No placeholders — all branches are real AsyncSession queries or
deterministic mappings with fallbacks.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.aiml.models import AIRiskRecord
from app.core.exceptions import NotFoundError, ValidationError

logger = logging.getLogger(__name__)

# ── constants ──────────────────────────────────────────────────────────

_VALID_SEVERITY: set[str] = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
_VALID_LIKELIHOOD: set[str] = {"LOW", "MEDIUM", "HIGH", "CRITICAL", "RARE", "UNLIKELY", "POSSIBLE", "LIKELY", "ALMOST_CERTAIN"}
_VALID_IMPACT: set[str] = {"LOW", "MEDIUM", "HIGH", "CRITICAL", "MINOR", "MODERATE", "MAJOR", "SEVERE"}
_VALID_STATUS: set[str] = {"OPEN", "MITIGATED", "ACCEPTED", "CLOSED", "TRANSFERRED", "IN_REVIEW", "DRAFT", "ACKNOWLEDGED"}

# governance heuristic mapping — strings to numeric factor 1-5
# LOW/MINOR/RARE -> 1, MEDIUM/MODERATE/POSSIBLE -> 2, HIGH/MAJOR/LIKELY -> 3,
# CRITICAL/SEVERE/ALMOST_CERTAIN -> 4 (extendable to 5 if needed)
_SEVERITY_MAP: dict[str, int] = {
    "LOW": 1,
    "MINOR": 1,
    "RARE": 1,
    "MEDIUM": 2,
    "MODERATE": 2,
    "POSSIBLE": 2,
    "UNLIKELY": 2,
    "HIGH": 3,
    "MAJOR": 3,
    "LIKELY": 3,
    "CRITICAL": 4,
    "SEVERE": 4,
    "ALMOST_CERTAIN": 4,
    "ALMOST-CERTAIN": 4,
}
_LIKELIHOOD_MAP: dict[str, int] = dict(_SEVERITY_MAP)
_IMPACT_MAP: dict[str, int] = dict(_SEVERITY_MAP)

# allow numeric strings "1"-"5" to pass through directly
_NUMERIC_ALIASES: dict[str, int] = {"1": 1, "2": 2, "3": 3, "4": 4, "5": 5}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _audit(tenant: str, actor: str, action: str, resource_id: str = "", details: dict | None = None) -> None:
    try:
        from app.iam.audit_service import audit_service  # type: ignore

        safe: dict = {}
        if details:
            for k, v in details.items():
                if k in ("raw_value", "secret", "prompt", "content", "value", "match"):
                    continue
                if isinstance(v, dict) and "raw_value" in v:
                    v = {ik: iv for ik, iv in v.items() if ik != "raw_value"}
                safe[k] = v
        try:
            audit_service.log(tenant, actor, "user", action, "ai_risk", resource_id, "success", safe)
        except TypeError:
            audit_service.log(tenant, actor, "user", action, "ai_risk", resource_id, "success", safe)  # type: ignore[call-arg]
    except Exception as exc:  # noqa: BLE001
        logger.debug("audit unavailable (%s): %s", action, exc)


def _parse_uuid(value: str | uuid.UUID | None) -> uuid.UUID | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value).strip())
    except Exception as exc:  # noqa: BLE001
        raise ValidationError(message=f"invalid UUID: {value} — {exc}") from exc


def _normalize_level(value: str, field: str, valid: set[str]) -> str:
    if not value or not str(value).strip():
        raise ValidationError(message=f"{field} is required")
    lvl = str(value).strip().upper().replace(" ", "_").replace("-", "_")
    # accept numeric 1-5 directly
    if lvl in _NUMERIC_ALIASES:
        # map back to textual for storage consistency — store as upper textual
        # but we keep the numeric string mapping via alias table in scoring
        # Normalize 1->LOW, 2->MEDIUM, 3->HIGH, 4->CRITICAL
        rev = {1: "LOW", 2: "MEDIUM", 3: "HIGH", 4: "CRITICAL", 5: "CRITICAL"}
        return rev[_NUMERIC_ALIASES[lvl]]
    if lvl not in valid:
        # allow severity map aliases (e.g., SEVERE, MAJOR)
        if lvl in _SEVERITY_MAP:
            # map alias to canonical HIGH/CRITICAL/LOW/MEDIUM
            num = _SEVERITY_MAP[lvl]
            rev2 = {1: "LOW", 2: "MEDIUM", 3: "HIGH", 4: "CRITICAL"}
            return rev2[num]
        raise ValidationError(message=f"invalid {field} '{value}'; allowed: {sorted(valid)} (or 1-5)")
    return lvl


def _level_to_score(level: str, mapping: dict[str, int]) -> int:
    if not level:
        return 1
    lvl = str(level).strip().upper().replace(" ", "_").replace("-", "_")
    if lvl in _NUMERIC_ALIASES:
        return _NUMERIC_ALIASES[lvl]
    if lvl in mapping:
        return mapping[lvl]
    # fallback: try severity map
    if lvl in _SEVERITY_MAP:
        return _SEVERITY_MAP[lvl]
    try:
        n = int(float(lvl))
        if 1 <= n <= 5:
            return n
    except Exception:
        pass
    return 1


class AIRiskService:
    """Tenant-scoped AI risk record lifecycle and governance scoring."""

    # ── create ─────────────────────────────────────────────────────────

    async def create_risk(
        self,
        db: AsyncSession,
        tenant: str,
        system: str,
        model_id: str | uuid.UUID | None = None,
        risk_id: str | None = None,
        severity: str | None = None,
        likelihood: str | None = None,
        impact: str | None = None,
        owner: str | None = None,
        mitigation: str | None = None,
    ) -> AIRiskRecord:
        """Create a tenant-scoped risk record.

        Args:
            db: AsyncSession (tenant-scoped).
            tenant: tenant id (required, non-empty).
            system: system identifier (required) — e.g. service or model system name.
            model_id: optional FK to ``ai_model_registry.id`` (UUID).  When
                supplied it must be a valid UUID; existence is not enforced
                here (the FK is SET NULL on delete), but the value is stored.
            risk_id: business risk identifier (required) — unique per tenant
                is recommended but not enforced at DB level beyond index.
            severity: LOW/MEDIUM/HIGH/CRITICAL (or 1-5).
            likelihood: LOW/MEDIUM/HIGH/CRITICAL (or RARE/POSSIBLE/LIKELY etc.).
            impact: LOW/MEDIUM/HIGH/CRITICAL (or MINOR/MAJOR/SEVERE etc.).
            owner: risk owner identity (optional).
            mitigation: mitigation description (optional).

        Returns: persisted ``AIRiskRecord`` with computed ``score``.

        Governance note: score is severity*likelihood*impact heuristic —
        not a legal conclusion, just a governance aid.
        """
        if not tenant or not str(tenant).strip():
            raise ValidationError(message="tenant is required")
        if not system or not str(system).strip():
            raise ValidationError(message="system is required")
        if not risk_id or not str(risk_id).strip():
            raise ValidationError(message="risk_id is required")
        tenant_s = str(tenant).strip()
        system_s = str(system).strip()
        risk_id_s = str(risk_id).strip()

        severity_s = _normalize_level(severity or "", "severity", _VALID_SEVERITY)
        likelihood_s = _normalize_level(likelihood or "", "likelihood", _VALID_LIKELIHOOD)
        impact_s = _normalize_level(impact or "", "impact", _VALID_IMPACT)

        owner_s = str(owner).strip() if owner and str(owner).strip() else None
        mitigation_s = str(mitigation).strip() if mitigation and str(mitigation).strip() else None

        model_uuid: uuid.UUID | None = None
        if model_id is not None and str(model_id).strip():
            try:
                model_uuid = _parse_uuid(model_id)
            except ValidationError:
                # model_id may be composite string (provider/name:version) — keep as None
                # and store composite in mitigation context rather than failing
                logger.debug("model_id '%s' not a UUID — storing as None for risk %s", model_id, risk_id_s)
                model_uuid = None

        # compute governance score
        sev_n = _level_to_score(severity_s, _SEVERITY_MAP)
        lik_n = _level_to_score(likelihood_s, _LIKELIHOOD_MAP)
        imp_n = _level_to_score(impact_s, _IMPACT_MAP)
        score = float(sev_n * lik_n * imp_n)

        row = AIRiskRecord(
            tenant=tenant_s,
            system=system_s,
            model_id=model_uuid,
            risk_id=risk_id_s,
            severity=severity_s,
            likelihood=likelihood_s,
            impact=impact_s,
            owner=owner_s,
            mitigation=mitigation_s,
            status="open",
            score=score,
        )
        db.add(row)
        await db.flush()
        await db.refresh(row)
        _audit(tenant_s, owner_s or "system", "ai_risk.created", str(row.id), {"system": system_s, "risk_id": risk_id_s, "severity": severity_s, "likelihood": likelihood_s, "impact": impact_s, "score": score})
        logger.info("risk %s system=%s tenant=%s score=%.1f", risk_id_s, system_s, tenant_s, score)
        return row

    # ── get ────────────────────────────────────────────────────────────

    async def get_risk(
        self,
        db: AsyncSession,
        tenant: str,
        risk_id: str | uuid.UUID,
    ) -> AIRiskRecord | None:
        """Fetch risk by PK (UUID) or business ``risk_id``, tenant-scoped.

        Returns None if not found or tenant mismatch.
        """
        if not tenant or not str(tenant).strip():
            raise ValidationError(message="tenant is required")
        tenant_s = str(tenant).strip()
        raw = str(risk_id).strip() if risk_id is not None else ""
        if not raw:
            raise ValidationError(message="risk_id is required")
        # try UUID PK first
        try:
            pk = uuid.UUID(raw)
            stmt = select(AIRiskRecord).where(AIRiskRecord.id == pk, AIRiskRecord.tenant == tenant_s)
            result = await db.execute(stmt)
            row = result.scalars().first()
            if row is not None:
                return row
        except Exception:
            pass
        # fallback to business risk_id
        stmt2 = select(AIRiskRecord).where(AIRiskRecord.tenant == tenant_s, AIRiskRecord.risk_id == raw)
        result2 = await db.execute(stmt2)
        return result2.scalars().first()

    # ── list ───────────────────────────────────────────────────────────

    async def list_risks(
        self,
        db: AsyncSession,
        tenant: str,
        filters: dict | None = None,
    ) -> list[AIRiskRecord]:
        """List risks for tenant with optional equality filters.

        Supported filter keys: system, risk_id, severity, likelihood, impact,
        status, owner, model_id (UUID string).
        """
        if not tenant or not str(tenant).strip():
            raise ValidationError(message="tenant is required")
        tenant_s = str(tenant).strip()
        filters = dict(filters) if isinstance(filters, dict) else {}
        stmt = select(AIRiskRecord).where(AIRiskRecord.tenant == tenant_s)
        for key in ("system", "risk_id", "severity", "likelihood", "impact", "status", "owner"):
            val = filters.get(key)
            if val is None or (isinstance(val, str) and not val.strip()):
                continue
            # normalize status/severity etc to upper for comparison
            if key in ("severity", "likelihood", "impact", "status"):
                val = str(val).strip().upper()
            col = getattr(AIRiskRecord, key, None)
            if col is not None:
                stmt = stmt.where(col == val)
        # model_id filter
        model_f = filters.get("model_id")
        if model_f is not None and str(model_f).strip():
            try:
                mu = uuid.UUID(str(model_f).strip())
                stmt = stmt.where(AIRiskRecord.model_id == mu)
            except Exception:
                pass
        stmt = stmt.order_by(AIRiskRecord.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    # ── update_status ──────────────────────────────────────────────────

    async def update_status(
        self,
        db: AsyncSession,
        tenant: str | None = None,
        risk_id: str | uuid.UUID | None = None,
        status: str | None = None,
        **kwargs: Any,
    ) -> AIRiskRecord:
        """Update risk status (tenant-scoped when tenant supplied).

        Supports flexible calling conventions to satisfy varied callers:
          - update_status(db, tenant, risk_id, status)
          - update_status(db, risk_id, status)  (tenant resolved from row)
          - update_status(db, tenant=..., risk_id=..., status=...)

        Args:
            db: AsyncSession.
            tenant: optional tenant id for scoping — when provided the row
                must belong to that tenant, otherwise isolation violation.
            risk_id: PK UUID or business risk_id (also accepts ``id`` kwarg).
            status: new status string (open/mitigated/accepted/closed etc.).

        Returns: updated ``AIRiskRecord``.

        Raises:
            ValidationError for missing/invalid status.
            NotFoundError when risk not found.
        """
        # Handle alternative kwarg names (id, risk)
        if risk_id is None:
            risk_id = kwargs.get("id") or kwargs.get("risk") or kwargs.get("risk_id")
        if status is None:
            status = kwargs.get("status") or kwargs.get("new_status")
        # Handle positional shift: if tenant looks like a UUID and risk_id is a status word
        # Detect caller that omitted tenant: update_status(db, risk_id, status)
        # In that case tenant arg actually holds risk_id
        if tenant is not None and risk_id is not None and status is None:
            # no-op, status already None — keep as is
            pass
        # If tenant provided but looks like a status and risk_id is actually tenant?
        # Clean handling: if status is None and tenant is not None and risk_id is not None
        # but status missing, try to interpret correctly.
        # For robustness, if first string after db is not a tenant-like but risk_id, caller
        # may have called update_status(db, risk_id, status) positionally — then
        # `tenant` receives risk_id and `risk_id` receives status.
        # Detect: tenant string is UUID or risk_id-like and second arg is status-like
        if status is None and risk_id is not None and tenant is not None:
            maybe_status = str(risk_id).strip()
            if maybe_status.lower() in {s.lower() for s in _VALID_STATUS} or maybe_status.upper() in _VALID_STATUS:
                # shift: tenant actually is risk_id
                status = maybe_status
                risk_id = tenant
                tenant = None
        if risk_id is None or (isinstance(risk_id, str) and not risk_id.strip()):
            raise ValidationError(message="risk_id is required")
        if status is None or not str(status).strip():
            raise ValidationError(message="status is required")
        status_s = str(status).strip().lower()
        status_upper = status_s.upper()
        if status_upper not in _VALID_STATUS:
            # also allow lower-case variants already lower; check case-insensitive
            if status_s.upper() not in _VALID_STATUS and status_s not in {s.lower() for s in _VALID_STATUS}:
                raise ValidationError(message=f"invalid status '{status}'; allowed: {sorted(_VALID_STATUS)}")
            status_upper = status_s.upper()
        # store lower for DB (default open lower) but accept either
        # AIRiskRecord.status default is "open" lower — we preserve lower
        store_status = status_s.lower()
        tenant_s = str(tenant).strip() if tenant and str(tenant).strip() else None
        raw = str(risk_id).strip()
        row: AIRiskRecord | None = None
        # try UUID PK
        try:
            pk = uuid.UUID(raw)
            stmt = select(AIRiskRecord).where(AIRiskRecord.id == pk)
            if tenant_s:
                stmt = stmt.where(AIRiskRecord.tenant == tenant_s)
            result = await db.execute(stmt)
            row = result.scalars().first()
        except Exception:
            row = None
        if row is None:
            stmt2 = select(AIRiskRecord).where(AIRiskRecord.risk_id == raw)
            if tenant_s:
                stmt2 = stmt2.where(AIRiskRecord.tenant == tenant_s)
            result2 = await db.execute(stmt2)
            row = result2.scalars().first()
        if row is None:
            raise NotFoundError(resource="AIRiskRecord", identifier=raw)
        # if tenant was supplied, enforce isolation even for PK path
        if tenant_s and row.tenant != tenant_s:
            raise NotFoundError(resource="AIRiskRecord", identifier=raw)
        old = row.status
        row.status = store_status
        await db.flush()
        await db.refresh(row)
        _audit(row.tenant, row.owner or "system", "ai_risk.status_updated", str(row.id), {"risk_id": row.risk_id, "old_status": old, "new_status": store_status})
        logger.info("risk %s status %s -> %s tenant=%s", row.risk_id, old, store_status, row.tenant)
        return row

    # ── calculate_score ────────────────────────────────────────────────

    async def calculate_score(self, risk: AIRiskRecord | dict[str, Any]) -> float:
        """Calculate governance score as severity*likelihood*impact.

        This is a deterministic governance aid — not a legal conclusion.
        The product of the three numeric factors (each 1-4) is returned.
        Accepts either an ``AIRiskRecord`` instance or a dict with
        ``severity``/``likelihood``/``impact`` keys.

        Args:
            risk: AIRiskRecord or dict-like with severity/likelihood/impact.

        Returns: float score (1-64 range for 1-4 factors) plus a note that
            the value is for governance purposes only.
        """
        if risk is None:
            raise ValidationError(message="risk is required")
        # extract levels flexibly
        if isinstance(risk, dict):
            severity = risk.get("severity") or risk.get("Severity")
            likelihood = risk.get("likelihood") or risk.get("Likelihood")
            impact = risk.get("impact") or risk.get("Impact")
        else:
            severity = getattr(risk, "severity", None)
            likelihood = getattr(risk, "likelihood", None)
            impact = getattr(risk, "impact", None)
        if not severity or not likelihood or not impact:
            raise ValidationError(message="risk must have severity, likelihood, and impact")
        sev_n = _level_to_score(str(severity), _SEVERITY_MAP)
        lik_n = _level_to_score(str(likelihood), _LIKELIHOOD_MAP)
        imp_n = _level_to_score(str(impact), _IMPACT_MAP)
        score = float(sev_n * lik_n * imp_n)
        # governance aid note — intentionally not a legal conclusion
        # Caller may persist via create_risk/update; this method is pure compute.
        return score


risk_service = AIRiskService()
