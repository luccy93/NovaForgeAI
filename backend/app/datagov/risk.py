"""Volume 57 — RiskService (decision-support risk scoring, not legal conclusion).

Calculates a 0-100 score, level low/medium/high/critical, and factors list
using configurable weights over:

  - classification  (PUBLIC/INTERNAL/CONFIDENTIAL/RESTRICTED/SECRET)
  - exposure        (location, sharing, internet-facing, export)
  - access          (owner, grants, processor count)
  - provider        (third-party risk, unknown provider)
  - region          (cross-border, residency)
  - policy_status   (policy decisions DENY/REQUIRE_APPROVAL, DLP violations)
  - control_failures (failed controls, expired evidence)

All inputs are derived from governance tables and asset metadata — no raw
secret values. Result is stored best-effort in asset metadata_json
(governance_risk) but persistence is not required. Caller must treat output
as decision support only.

Tenant-scoped, AsyncSession, audit best-effort, no placeholders.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.datagov.models import GovernanceDataAsset

logger = logging.getLogger(__name__)

# ── classification severity ─────────────────────────────────────────────

_CLASSIFICATION_SCORE: dict[str, int] = {
    "PUBLIC": 5,
    "INTERNAL": 20,
    "CONFIDENTIAL": 50,
    "RESTRICTED": 80,
    "SECRET": 100,
    # legacy
    "REGULATED": 80,
}

# ── default weights (sum = 1.0) ─────────────────────────────────────────

DEFAULT_WEIGHTS: dict[str, float] = {
    "classification": 0.25,
    "exposure": 0.15,
    "access": 0.15,
    "provider": 0.10,
    "region": 0.10,
    "policy_status": 0.15,
    "control_failures": 0.10,
}

# order for deterministic factors list
_WEIGHT_KEYS: list[str] = ["classification", "exposure", "access", "provider", "region", "policy_status", "control_failures"]


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
                "governance_risk",
                resource_id,
                "success",
                details or {},
            )
        except TypeError:
            audit_service.log(tenant, actor, "user", action, "governance_risk", resource_id, "success", details or {})
    except Exception as exc:  # noqa: BLE001
        logger.debug("audit unavailable (%s): %s", action, exc)


def _normalize_weights(weights: dict[str, float] | None) -> dict[str, float]:
    if not weights:
        return dict(DEFAULT_WEIGHTS)
    # merge with defaults, ignore unknown keys
    out: dict[str, float] = {}
    for k in _WEIGHT_KEYS:
        if k in weights:
            try:
                v = float(weights[k])
            except Exception:
                raise ValueError(f"weight '{k}' must be numeric")
            if not 0 <= v <= 1:
                raise ValueError(f"weight '{k}' must be between 0 and 1")
            out[k] = v
        else:
            out[k] = float(DEFAULT_WEIGHTS[k])
    # normalize to sum 1.0 if not already (allow small drift)
    total = sum(out.values())
    if total == 0:
        raise ValueError("weights sum cannot be zero")
    if abs(total - 1.0) > 0.001:
        out = {k: v / total for k, v in out.items()}
    return out


def _classification_score(level: str | None) -> tuple[int, str]:
    if not level:
        return 20, "classification empty — default INTERNAL (20)"
    lvl = str(level).strip().upper()
    if lvl in _CLASSIFICATION_SCORE:
        s = _CLASSIFICATION_SCORE[lvl]
        return s, f"classification {lvl} severity {s}"
    return 20, f"classification unknown '{level}' — default INTERNAL (20)"


def _level_from_score(score: int) -> str:
    if score >= 80:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 30:
        return "medium"
    return "low"


class RiskService:
    """Decision-support risk scoring (not legal conclusion)."""

    def __init__(self, weights: dict[str, float] | None = None):
        self.weights = _normalize_weights(weights)

    async def calculate_risk(
        self,
        db: AsyncSession,
        tenant: str,
        asset_id: str,
        weights: dict[str, float] | None = None,
        persist: bool = True,
    ) -> dict[str, Any]:
        """Calculate risk for a data asset.

        Args:
            db: AsyncSession (tenant-scoped).
            tenant: tenant scope (required).
            asset_id: GovernanceDataAsset asset_id (required).
            weights: optional override weights (dict with keys in
                   classification/exposure/access/provider/region/
                   policy_status/control_failures). Values 0-1, normalized
                   to sum 1.0 if needed. If None, uses service defaults.
            persist: if True, store result best-effort in asset
                   metadata_json.governance_risk and also in a separate
                   cache dict on the instance (_risk_cache). Not required
                   to persist — if storage fails, score is still returned.

        Returns:
            dict with:
              - score (0-100 int)
              - level (low/medium/high/critical)
              - factors (list[dict] each with key, score, weight, contribution, reason)
              - weights (effective weights used)
              - asset_id, tenant
              - disclaimer ("decision support only, not legal conclusion")
              - metadata (asset classification, exposure hints etc.)
        """
        if not tenant or not str(tenant).strip():
            raise ValueError("tenant is required")
        if not asset_id or not str(asset_id).strip():
            raise ValueError("asset_id is required")
        tenant_s = str(tenant).strip()
        asset_id_s = str(asset_id).strip()

        eff_weights = _normalize_weights(weights) if weights is not None else dict(self.weights)

        # ── 1. fetch asset ──────────────────────────────────────────────
        stmt = select(GovernanceDataAsset).where(
            GovernanceDataAsset.tenant == tenant_s,
            GovernanceDataAsset.asset_id == asset_id_s,
        )
        result = await db.execute(stmt)
        asset: GovernanceDataAsset | None = result.scalars().first()
        if asset is None:
            raise ValueError(f"asset '{asset_id_s}' not found for tenant '{tenant_s}'")

        # convenience
        mj: dict = dict(asset.metadata_json or {}) if isinstance(asset.metadata_json, dict) else {}
        classification = (asset.classification or "INTERNAL").strip().upper()
        location = asset.location or ""
        resource = asset.resource or ""
        asset_type = getattr(asset, "type", "") or ""

        factors: list[dict[str, Any]] = []
        raw_scores: dict[str, int] = {}

        # ── 2. classification ───────────────────────────────────────────
        c_score, c_reason = _classification_score(classification)
        raw_scores["classification"] = c_score
        factors.append(
            {
                "key": "classification",
                "score": c_score,
                "weight": eff_weights["classification"],
                "contribution": round(c_score * eff_weights["classification"], 2),
                "reason": c_reason,
            }
        )

        # ── 3. exposure ─────────────────────────────────────────────────
        # exposure heuristics: location public/internet, export lineage, sharing flags
        exposure_score = 20
        exposure_reasons: list[str] = []
        loc_low = str(location).lower() if location else ""
        res_low = str(resource).lower() if resource else ""
        mj_str = str(mj).lower()
        # internet-facing markers
        if any(m in loc_low for m in ("public", "internet", "external", "cdn")) or any(m in res_low for m in ("public", "external")):
            exposure_score = max(exposure_score, 80)
            exposure_reasons.append("location/resource indicates public/internet exposure (+80)")
        elif any(m in loc_low for m in ("shared", "bucket", "s3")):
            exposure_score = max(exposure_score, 50)
            exposure_reasons.append("shared storage exposure (+50)")
        # export/lineage exposure: check lineage downstream or metadata export flags
        try:
            from app.datagov.models import GovernanceLineage

            l_stmt = select(GovernanceLineage).where(
                GovernanceLineage.tenant == tenant_s,
                GovernanceLineage.source_asset == asset_id_s,
                GovernanceLineage.stage.in_(["export", "output"]),  # type: ignore
            )
            lres = await db.execute(l_stmt)
            export_edges = list(lres.scalars().all())
            if export_edges:
                exposure_score = max(exposure_score, 70)
                exposure_reasons.append(f"export/output lineage detected ({len(export_edges)} edges) (+70)")
        except Exception as exc:  # noqa: BLE001
            logger.debug("exposure lineage check failed: %s", exc)

        if mj.get("exposure") or mj.get("shared") or mj.get("public"):
            val = mj.get("exposure") or mj.get("shared") or mj.get("public")
            if isinstance(val, bool) and val:
                exposure_score = max(exposure_score, 75)
                exposure_reasons.append("metadata exposure flag true (+75)")
            elif isinstance(val, str) and val.lower() in ("high", "public", "external", "shared"):
                exposure_score = max(exposure_score, 75)
                exposure_reasons.append(f"metadata exposure '{val}' (+75)")

        if mj.get("exposure_score") is not None:
            try:
                ms = int(mj.get("exposure_score"))
                exposure_score = max(exposure_score, min(100, max(0, ms)))
                exposure_reasons.append(f"metadata exposure_score {ms}")
            except Exception:
                pass

        if not exposure_reasons:
            exposure_reasons.append(f"no exposure markers — baseline {exposure_score}")

        raw_scores["exposure"] = exposure_score
        factors.append(
            {
                "key": "exposure",
                "score": exposure_score,
                "weight": eff_weights["exposure"],
                "contribution": round(exposure_score * eff_weights["exposure"], 2),
                "reason": "; ".join(exposure_reasons),
            }
        )

        # ── 4. access ────────────────────────────────────────────────────
        access_score = 20
        access_reasons: list[str] = []
        # owner missing => higher risk
        if not asset.owner:
            access_score = max(access_score, 50)
            access_reasons.append("no owner assigned (+50)")
        else:
            access_reasons.append(f"owner {asset.owner} assigned")
        # access grants via processors or metadata
        grant_count = 0
        try:
            from app.datagov.models import GovernanceProcessor

            p_stmt = select(GovernanceProcessor).where(GovernanceProcessor.tenant == tenant_s)
            pres = await db.execute(p_stmt)
            processors = list(pres.scalars().all())
            for p in processors:
                grants = p.access_grants or []
                for g in grants:
                    if not isinstance(g, dict):
                        continue
                    if g.get("grant_id") is None and g.get("action"):
                        continue  # audit entry
                    # match resource containing asset_id or resource
                    g_res = str(g.get("resource") or "").lower()
                    if asset_id_s.lower() in g_res or str(resource).lower() in g_res or g_res == "*":
                        grant_count += 1
        except Exception as exc:  # noqa: BLE001
            logger.debug("access grant count failed: %s", exc)

        # also metadata access grants
        if isinstance(mj.get("access_grants"), list):
            grant_count += len([g for g in mj.get("access_grants") if isinstance(g, dict)])
        if isinstance(mj.get("grants"), list):
            grant_count += len(mj.get("grants"))

        if grant_count > 0:
            # each grant adds risk, capped
            grant_risk = min(100, 30 + grant_count * 15)
            access_score = max(access_score, grant_risk)
            access_reasons.append(f"{grant_count} third-party access grants (+{grant_risk})")
        # metadata access level
        if mj.get("access") and isinstance(mj.get("access"), str):
            a_low = str(mj.get("access")).lower()
            if a_low in ("public", "open", "anyone"):
                access_score = max(access_score, 90)
                access_reasons.append(f"access metadata '{a_low}' (+90)")
            elif a_low in ("restricted", "private"):
                access_reasons.append(f"access metadata '{a_low}' (no increase)")

        if not access_reasons or len(access_reasons) == 1 and "assigned" in access_reasons[0]:
            access_reasons.append(f"baseline access risk {access_score}")

        raw_scores["access"] = access_score
        factors.append(
            {
                "key": "access",
                "score": access_score,
                "weight": eff_weights["access"],
                "contribution": round(access_score * eff_weights["access"], 2),
                "reason": "; ".join(access_reasons),
            }
        )

        # ── 5. provider ─────────────────────────────────────────────────
        provider_score = 20
        provider_reasons: list[str] = []
        provider_hint = ""
        # infer provider from asset source, metadata provider, or processors linked
        if isinstance(mj.get("provider"), str) and mj.get("provider"):
            provider_hint = str(mj.get("provider")).strip()
        elif asset.source and str(asset.source).strip():
            provider_hint = str(asset.source).strip()
        # check processor provider linking to this asset
        linked_providers: list[str] = []
        try:
            from app.datagov.models import GovernanceProcessor

            p_stmt2 = select(GovernanceProcessor).where(GovernanceProcessor.tenant == tenant_s)
            pres2 = await db.execute(p_stmt2)
            for p in list(pres2.scalars().all()):
                # heuristic: processor purpose/resource linkage
                if provider_hint and provider_hint.lower() in p.provider.lower():
                    linked_providers.append(p.provider)
        except Exception:
            pass

        if provider_hint:
            # unknown provider => higher risk; known high-risk markers
            ph_low = provider_hint.lower()
            if ph_low in ("unknown", "external", "third_party", "third-party"):
                provider_score = 85
                provider_reasons.append(f"provider '{provider_hint}' unknown/external (+85)")
            elif any(x in ph_low for x in ("openai", "anthropic", "external_api")):
                # external LLM provider risk depends on classification
                if classification in ("RESTRICTED", "SECRET"):
                    provider_score = 90
                    provider_reasons.append(f"external LLM provider '{provider_hint}' with {classification} data (+90)")
                else:
                    provider_score = 50
                    provider_reasons.append(f"external provider '{provider_hint}' (+50)")
            else:
                provider_reasons.append(f"provider '{provider_hint}' baseline {provider_score}")
        else:
            provider_reasons.append(f"no provider linked — baseline {provider_score}")

        if linked_providers:
            provider_reasons.append(f"linked processors {linked_providers}")

        raw_scores["provider"] = provider_score
        factors.append(
            {
                "key": "provider",
                "score": provider_score,
                "weight": eff_weights["provider"],
                "contribution": round(provider_score * eff_weights["provider"], 2),
                "reason": "; ".join(provider_reasons),
            }
        )

        # ── 6. region ────────────────────────────────────────────────────
        region_score = 10
        region_reasons: list[str] = []
        region_hint: str | None = None
        if isinstance(mj.get("region"), str) and mj.get("region"):
            region_hint = str(mj.get("region")).strip()
        elif isinstance(mj.get("processing_region"), str) and mj.get("processing_region"):
            region_hint = str(mj.get("processing_region")).strip()
        elif location and isinstance(location, str) and location.strip():
            # try to extract region from location string (last segment)
            region_hint = str(location).strip().split("/")[-1].split(":")[-1]
        # cross-border check vs processors
        cross_border = False
        try:
            from app.datagov.models import GovernanceProcessor

            p_stmt3 = select(GovernanceProcessor).where(GovernanceProcessor.tenant == tenant_s)
            pres3 = await db.execute(p_stmt3)
            for p in list(pres3.scalars().all()):
                if p.region and region_hint:
                    if str(p.region).strip().lower() != str(region_hint).strip().lower():
                        cross_border = True
                        break
                    if "cross" in str(p.region).lower() or "external" in str(p.region).lower():
                        cross_border = True
                        break
        except Exception:
            pass

        # metadata cross-border flag
        if mj.get("cross_border") is True or mj.get("cross-border") is True:
            cross_border = True

        if cross_border:
            if classification in ("RESTRICTED", "SECRET"):
                region_score = 90
                region_reasons.append(f"cross-border processing for {classification} data (+90)")
            elif classification == "CONFIDENTIAL":
                region_score = 60
                region_reasons.append("cross-border for CONFIDENTIAL (+60)")
            else:
                region_score = 40
                region_reasons.append("cross-border for non-restricted (+40)")
        else:
            region_reasons.append(f"no cross-border detected — baseline {region_score}")
            if region_hint:
                region_reasons.append(f"region '{region_hint}'")

        raw_scores["region"] = region_score
        factors.append(
            {
                "key": "region",
                "score": region_score,
                "weight": eff_weights["region"],
                "contribution": round(region_score * eff_weights["region"], 2),
                "reason": "; ".join(region_reasons),
            }
        )

        # ── 7. policy_status ────────────────────────────────────────────
        policy_score = 10
        policy_reasons: list[str] = []
        # check recent policy decisions for this asset/resource
        try:
            from app.datagov.models import GovernancePolicyDecision, GovernanceDLPEvent

            # policy decisions where resource matches asset_id or resource
            pd_stmt = select(GovernancePolicyDecision).where(
                GovernancePolicyDecision.tenant == tenant_s,
                GovernancePolicyDecision.resource.in_([asset_id_s, resource]),  # type: ignore
            ).order_by(GovernancePolicyDecision.created_at.desc()).limit(10)
            pd_res = await db.execute(pd_stmt)
            decisions = list(pd_res.scalars().all())
            for d in decisions:
                dec = str(d.decision).upper()
                if dec == "DENY":
                    policy_score = max(policy_score, 95)
                    policy_reasons.append(f"policy DENY for '{d.resource}' ({d.policy_id}) (+95)")
                elif dec == "REQUIRE_APPROVAL":
                    policy_score = max(policy_score, 70)
                    policy_reasons.append(f"policy REQUIRE_APPROVAL for '{d.resource}' (+70)")
                elif dec == "REDACT":
                    policy_score = max(policy_score, 50)
                    policy_reasons.append(f"policy REDACT for '{d.resource}' (+50)")

            # DLP violations where resource matches
            dlp_stmt = select(GovernanceDLPEvent).where(
                GovernanceDLPEvent.tenant == tenant_s,
            ).order_by(GovernanceDLPEvent.created_at.desc()).limit(20)
            dlp_res = await db.execute(dlp_stmt)
            dlp_events = list(dlp_res.scalars().all())
            for ev in dlp_events:
                res_low = str(ev.resource or "").lower()
                if asset_id_s.lower() in res_low or str(resource).lower() in res_low:
                    if ev.action in ("BLOCK", "REQUIRE_APPROVAL") or ev.event_type == "violation":
                        policy_score = max(policy_score, 85)
                        policy_reasons.append(f"DLP violation BLOCK for '{ev.resource}' (+85)")
                    elif ev.action == "REDACT":
                        policy_score = max(policy_score, 45)
                        policy_reasons.append(f"DLP redact for '{ev.resource}' (+45)")
        except Exception as exc:  # noqa: BLE001
            logger.debug("policy_status check failed: %s", exc)

        if mj.get("policy_status") and isinstance(mj.get("policy_status"), str):
            ps = str(mj.get("policy_status")).strip().lower()
            if ps in ("violation", "denied", "blocked"):
                policy_score = max(policy_score, 90)
                policy_reasons.append(f"metadata policy_status '{ps}' (+90)")
            elif ps in ("requires_approval", "pending"):
                policy_score = max(policy_score, 60)
                policy_reasons.append(f"metadata policy_status '{ps}' (+60)")

        if not policy_reasons:
            policy_reasons.append(f"no policy violations — baseline {policy_score}")

        raw_scores["policy_status"] = policy_score
        factors.append(
            {
                "key": "policy_status",
                "score": policy_score,
                "weight": eff_weights["policy_status"],
                "contribution": round(policy_score * eff_weights["policy_status"], 2),
                "reason": "; ".join(policy_reasons),
            }
        )

        # ── 8. control_failures ─────────────────────────────────────────
        control_score = 10
        control_reasons: list[str] = []
        try:
            from app.datagov.models import GovernanceControl

            c_stmt = select(GovernanceControl).where(GovernanceControl.tenant == tenant_s).order_by(GovernanceControl.created_at.desc()).limit(50)
            cres = await db.execute(c_stmt)
            controls = list(cres.scalars().all())
            failed = 0
            partial = 0
            not_assessed = 0
            for c in controls:
                st = str(c.status).upper()
                if st == "FAIL":
                    failed += 1
                elif st == "PARTIAL":
                    partial += 1
                elif st == "NOT_ASSESSED":
                    not_assessed += 1
            # asset-specific control mapping via policy_id linkage in metadata
            # if asset references controls, weight those; otherwise use global signal dampened
            if failed > 0:
                # global failure signal — not asset-specific, so dampen
                control_score = max(control_score, min(90, 40 + failed * 15))
                control_reasons.append(f"{failed} failed controls in tenant (+{control_score})")
            if partial > 0:
                control_score = max(control_score, min(70, 25 + partial * 10))
                control_reasons.append(f"{partial} partial controls")
            if not_assessed > 5:
                control_score = max(control_score, 35)
                control_reasons.append(f"{not_assessed} not-assessed controls (+35)")

            # asset-linked controls via metadata
            linked_controls = mj.get("controls") or mj.get("control_ids") or []
            if isinstance(linked_controls, list) and linked_controls:
                # look up those specific controls
                linked_failed = 0
                for cid in linked_controls:
                    for c in controls:
                        if str(c.control_id) == str(cid) or str(c.id) == str(cid):
                            if str(c.status).upper() in ("FAIL", "PARTIAL"):
                                linked_failed += 1
                if linked_failed:
                    control_score = max(control_score, min(100, 60 + linked_failed * 20))
                    control_reasons.append(f"{linked_failed} asset-linked control failures (+{control_score})")
        except Exception as exc:  # noqa: BLE001
            logger.debug("control_failures check failed: %s", exc)

        if mj.get("control_failures") is not None:
            try:
                cf = int(mj.get("control_failures"))
                control_score = max(control_score, min(100, 20 + cf * 20))
                control_reasons.append(f"metadata control_failures {cf}")
            except Exception:
                pass

        if not control_reasons:
            control_reasons.append(f"no control failures — baseline {control_score}")

        raw_scores["control_failures"] = control_score
        factors.append(
            {
                "key": "control_failures",
                "score": control_score,
                "weight": eff_weights["control_failures"],
                "contribution": round(control_score * eff_weights["control_failures"], 2),
                "reason": "; ".join(control_reasons),
            }
        )

        # ── 9. weighted sum ─────────────────────────────────────────────
        total = 0.0
        for f in factors:
            total += float(f["score"]) * float(f["weight"])
        score = int(round(max(0, min(100, total))))
        level = _level_from_score(score)

        result: dict[str, Any] = {
            "score": score,
            "level": level,
            "factors": factors,
            "raw_scores": raw_scores,
            "weights": eff_weights,
            "asset_id": asset_id_s,
            "tenant": tenant_s,
            "classification": classification,
            "resource": resource,
            "type": asset_type,
            "disclaimer": "decision support only, not legal conclusion",
            "calculated_at": _utc_now().isoformat(),
            "metadata": {
                "location": location,
                "owner": asset.owner,
                "sensitivity": asset.sensitivity,
                "retention_policy": asset.retention_policy,
            },
        }

        # ── 10. persist best-effort ─────────────────────────────────────
        if persist:
            try:
                meta = dict(asset.metadata_json or {})
                meta["governance_risk"] = {
                    "score": score,
                    "level": level,
                    "factors": factors,
                    "weights": eff_weights,
                    "calculated_at": result["calculated_at"],
                    "disclaimer": result["disclaimer"],
                }
                meta["risk_score"] = score
                meta["risk_level"] = level
                asset.metadata_json = meta
                await db.flush()
                # also keep instance cache (separate, not required to persist)
                if not hasattr(self, "_risk_cache"):
                    self._risk_cache: dict[str, dict[str, Any]] = {}
                self._risk_cache[f"{tenant_s}:{asset_id_s}"] = dict(result)
            except Exception as exc:  # noqa: BLE001
                logger.debug("risk persist failed (non-blocking): %s", exc)

        _audit(tenant_s, "system", "governance.risk.calculated", asset_id_s, {"score": score, "level": level, "classification": classification})

        return result

    async def get_cached_risk(
        self,
        tenant: str,
        asset_id: str,
    ) -> dict[str, Any] | None:
        """Return last calculated risk from cache if available (not DB)."""
        key = f"{str(tenant).strip()}:{str(asset_id).strip()}"
        cache: dict[str, dict[str, Any]] = getattr(self, "_risk_cache", {})
        return cache.get(key)


risk_service = RiskService()
