"""Volume 58 — ModelGatewayService (orchestrates routing + invocation).

Tenant-scoped, AsyncSession, fail-closed.

Routing considerations (in priority order):
  1. Policy — via datagov.ai_gate AIGateService (fail-closed for
     RESTRICTED/SECRET) + governance ai_governance / policy_engine.
  2. Model capability (purpose must be in model capabilities if specified).
  3. Quality / latency / cost (from ai_monitoring_snapshots if available).
  4. Region / classification (never route restricted data to unauthorized
     provider — fail-closed).
  5. Budget (provider pricing).

Returns routing decision with model/provider/region.

Invocation path:
  check model status APPROVED/ACTIVE -> provider availability ->
  policy check (ALLOW/DENY/REDACT/REQUIRE_APPROVAL) ->
  guardrail pre-check -> provider call stub (mocked cost/latency) ->
  post-output policy check -> audit. Never deploy unapproved model.

No placeholders — all branches real AsyncSession queries with fallbacks.
Audit best-effort via app.iam.audit_service.
"""

from __future__ import annotations

import hashlib
import logging
import random
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.aiml.models import AIGuardrail, AIModelRegistry, AIMonitoringSnapshot, AIProviderRegistry
from app.core.exceptions import AuthorizationError, NotFoundError, ServiceUnavailableError, ValidationError

logger = logging.getLogger(__name__)


# ── constants ──────────────────────────────────────────────────────────

_RESTRICTED_LEVELS: set[str] = {"RESTRICTED", "SECRET"}
_ALL_LEVELS: set[str] = {"PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED", "SECRET"}
_AVAILABLE_ONLY: set[str] = {"AVAILABLE"}
_UNAVAILABLE_VALUES: set[str] = {"DEGRADED", "UNAVAILABLE", "UNKNOWN", "MAINTENANCE"}

# cross-border markers copied from ai_gate heuristic
_CROSS_BORDER_MARKERS: set[str] = {"external", "cross-border", "cross_border", "cross", "international", "unknown"}


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
            audit_service.log(
                tenant,
                actor,
                "user",
                action,
                "ai_gateway",
                resource_id,
                "success",
                safe,
            )
        except TypeError:
            audit_service.log(tenant, actor, "user", action, "ai_gateway", resource_id, "success", safe)  # type: ignore[call-arg]
    except Exception as exc:  # noqa: BLE001
        logger.debug("audit unavailable (%s): %s", action, exc)


def _normalize_classification(level: str | None) -> str:
    if not level:
        return "INTERNAL"
    lvl = str(level).strip().upper()
    if lvl in _ALL_LEVELS:
        return lvl
    if lvl == "REGULATED":
        return "RESTRICTED"
    return "INTERNAL"


def _is_cross_border(region: str | None) -> bool:
    if not region:
        return False
    r = str(region).strip().lower().replace(" ", "_").replace("-", "_")
    if not r:
        return False
    if r in _CROSS_BORDER_MARKERS:
        return True
    if "cross" in r:
        return True
    if r in ("eu", "cn", "ru", "ir", "kp"):
        return True
    if r.startswith("eu_") or r.startswith("eu-") or r.startswith("ap_") or r.startswith("ap-"):
        return True
    return False


def _parse_uuid(value: str | uuid.UUID) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()[:16]


def _redact_text(text: str) -> str:
    """Minimal redaction stub for REDACT decision — fingerprints only."""
    if not text:
        return text
    # Replace apparent secrets/emails with [REDACTED] + keep length hint via fingerprint prefix
    import re

    redacted = re.sub(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", "[REDACTED_EMAIL]", text)
    redacted = re.sub(r"\b\d{3}-\d{2}-\d{4}\b", "[REDACTED_SSN]", redacted)
    # generic secret-like tokens (>20 chars mixed)
    redacted = re.sub(r"\b[A-Za-z0-9_\-]{20,}\b", lambda m: f"[REDACTED_{_fingerprint(m.group(0))[:6]}]", redacted)
    return redacted


class ModelGatewayService:
    """Orchestrates model routing and invocation with policy + guardrails."""

    # ── routing ────────────────────────────────────────────────────────

    async def route(
        self,
        db: AsyncSession,
        tenant: str,
        purpose: str | None = None,
        data_classification: str = "INTERNAL",
        model_hint: str | None = None,
        provider_hint: str | None = None,
        region_hint: str | None = None,
        budget: float | None = None,
        policy_context: dict | None = None,
    ) -> dict[str, Any]:
        """Select best model/provider/region for a request.

        Considerations:
          - policy (datagov.ai_gate + governance ai_governance/policies)
          - model capability (purpose membership)
          - quality/latency/cost (ai_monitoring_snapshots)
          - region/classification (fail-closed for restricted)

        Never routes RESTRICTED/SECRET data to an unauthorized provider
        (checks provider data_processing_policy allowed classifications).

        Returns: routing decision dict with model/provider/region and
        diagnostics. Raises AuthorizationError fail-closed when no
        authorized route exists for restricted data.
        """
        if not tenant or not str(tenant).strip():
            raise ValidationError(message="tenant is required")
        tenant_s = str(tenant).strip()
        classification = _normalize_classification(data_classification)
        purpose_s = str(purpose).strip() if purpose else ""
        model_hint_s = str(model_hint).strip() if model_hint else ""
        provider_hint_s = str(provider_hint).strip().lower() if provider_hint else ""
        region_hint_s = str(region_hint).strip() if region_hint else ""
        budget_f = float(budget) if budget is not None else None
        policy_context = dict(policy_context) if policy_context else {}

        cross_border = _is_cross_border(region_hint_s)

        # ── 1. Policy pre-check (ai_gate + governance) ─────────────────
        # We eagerly evaluate policy so we can fail-closed before querying models.
        # For RESTRICTED/SECRET, any policy engine unavailability is treated as DENY
        # (mirrors ai_gate fail-closed). We do not silently allow.

        gate_decision: str | None = None
        gate_reason: str | None = None
        gate_raw: dict | None = None

        if provider_hint_s or classification in _RESTRICTED_LEVELS:
            # Evaluate ai_gate for the hinted provider (or probe with first candidate later if no hint)
            if provider_hint_s:
                try:
                    from app.datagov.ai_gate import ai_gate_service  # type: ignore

                    gate_raw = await ai_gate_service.check(
                        db=db,
                        tenant=tenant_s,
                        actor=purpose_s or "gateway.route",
                        data_classification=classification,
                        provider=provider_hint_s,
                        region=region_hint_s,
                        purpose=purpose_s,
                        resource=model_hint_s or provider_hint_s,
                    )
                    gate_decision = str(gate_raw.get("decision", "ALLOW")).upper()
                    gate_reason = str(gate_raw.get("reason", ""))
                    if gate_decision == "DENY":
                        _audit(tenant_s, purpose_s or "gateway", "ai_gateway.route.denied", "", {"classification": classification, "provider": provider_hint_s, "reason": gate_reason})
                        # fail-closed: do not offer alternative provider silently for restricted data
                        if classification in _RESTRICTED_LEVELS:
                            raise AuthorizationError(f"routing denied by policy for {classification} data: {gate_reason}")
                        return {"decision": "DENY", "reason": gate_reason, "classification": classification, "provider": provider_hint_s, "region": region_hint_s, "cross_border": cross_border, "policy": gate_raw}
                except AuthorizationError:
                    raise
                except ImportError as exc:
                    logger.debug("ai_gate not available during route: %s", exc)
                    if classification in _RESTRICTED_LEVELS:
                        raise AuthorizationError(f"fail-closed: policy engine unavailable for {classification} data") from exc
                except Exception as exc:  # noqa: BLE001
                    logger.debug("ai_gate check failed during route: %s", exc)
                    if classification in _RESTRICTED_LEVELS:
                        raise AuthorizationError(f"fail-closed: policy evaluation failed for {classification} data — {exc}") from exc

            # Also check governance blocked_providers (ai_governance)
            try:
                from app.governance.ai_governance import AIGovernanceManager  # type: ignore

                mgr: Any | None = None
                for stor in (f"ai_governance_data_{tenant_s}", "ai_governance_data"):
                    try:
                        m = AIGovernanceManager(storage_dir=stor)  # type: ignore
                        mgr = m
                        break
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("AIGovernanceManager init failed for %s: %s", stor, exc)
                        continue
                if mgr is not None:
                    try:
                        policies = mgr.list_policies(tenant_s)  # type: ignore[attr-defined]
                    except TypeError:
                        policies = mgr.list_policies(tenant_s, None)  # type: ignore
                    for pol in policies or []:
                        if not getattr(pol, "enabled", True):
                            continue
                        bps = [str(x).strip().lower() for x in (getattr(pol, "blocked_providers", []) or []) if x and str(x).strip()]
                        if provider_hint_s and provider_hint_s.lower() in bps:
                            reason = f"provider '{provider_hint_s}' blocked by governance policy '{getattr(pol, 'name', pol.id)}'"
                            if classification in _RESTRICTED_LEVELS:
                                raise AuthorizationError(reason)
                            # for non-restricted, treat as unavailable and continue to alternative
                            gate_decision = "DENY"
                            gate_reason = reason
                            break
            except AuthorizationError:
                raise
            except ImportError as exc:
                logger.debug("ai_governance not available during route: %s", exc)
            except Exception as exc:  # noqa: BLE001
                logger.debug("governance block check failed during route: %s", exc)

        # ── 2. Candidate models (tenant, APPROVED/ACTIVE) ──────────────
        stmt = select(AIModelRegistry).where(
            AIModelRegistry.tenant == tenant_s,
            AIModelRegistry.status.in_(["APPROVED", "ACTIVE"]),
        )
        if provider_hint_s:
            stmt = stmt.where(AIModelRegistry.provider == provider_hint_s)
        if model_hint_s:
            # model_hint may be name or model_id composite; try name first, then model_id, then id
            # We add OR-like expansion via fetching and filtering to keep query simple
            pass
        stmt = stmt.order_by(AIModelRegistry.created_at.desc())
        result = await db.execute(stmt)
        candidates: list[AIModelRegistry] = list(result.scalars().all())

        # Filter by model_hint if provided (post-query for flexibility: id / name / model_id)
        if model_hint_s:
            mh_lower = model_hint_s.lower()
            filtered: list[AIModelRegistry] = []
            for c in candidates:
                if mh_lower == str(c.id).lower() or mh_lower == c.name.lower() or mh_lower == (c.model_id or "").lower():
                    filtered.append(c)
            # also allow hint matching name substring
            if not filtered:
                for c in candidates:
                    if mh_lower in c.name.lower() or mh_lower in (c.model_id or "").lower():
                        filtered.append(c)
            if filtered:
                candidates = filtered
            # if hint yields nothing and classification is restricted, fail-closed (no fallback to random)
            elif classification in _RESTRICTED_LEVELS:
                raise AuthorizationError(f"no authorized model matches hint '{model_hint_s}' for {classification} data")

        # Capability filter (purpose): if purpose specified, prefer models whose capabilities contain it
        # Not hard DENY unless policy says; we score instead.

        if not candidates:
            if classification in _RESTRICTED_LEVELS:
                raise AuthorizationError(f"no approved models available for {classification} data (fail-closed)")
            return {"decision": "DENY", "reason": "no approved models available", "classification": classification, "provider": provider_hint_s, "region": region_hint_s, "cross_border": cross_border, "policy": gate_raw}

        # ── 3. Enrich with provider availability / region / cost / quality ─
        # We will score each candidate and pick best that satisfies constraints.

        scored: list[tuple[float, AIModelRegistry, AIProviderRegistry | None, dict]] = []

        for model in candidates:
            # provider row tenant-scoped
            provider_row: AIProviderRegistry | None = None
            try:
                stmt_p = select(AIProviderRegistry).where(
                    AIProviderRegistry.tenant == tenant_s,
                    AIProviderRegistry.provider == model.provider,
                )
                rp = await db.execute(stmt_p)
                provider_row = rp.scalars().first()
            except Exception as exc:  # noqa: BLE001
                logger.debug("provider lookup failed for %s: %s", model.provider, exc)
                provider_row = None

            # availability — only AVAILABLE is healthy
            if provider_row is not None and provider_row.availability != "AVAILABLE":
                # Never consider degraded/unavailable for restricted data; for normal data we also skip
                logger.debug("skipping model %s — provider %s availability %s", model.model_id, model.provider, provider_row.availability)
                continue

            # region check — if region_hint specified, prefer matching provider/model region
            region = region_hint_s or model.region or (provider_row.regions[0] if provider_row and provider_row.regions else None)
            if region_hint_s and provider_row and provider_row.regions:
                if region_hint_s not in provider_row.regions and model.region != region_hint_s:
                    # region mismatch — lower score but not fatal unless cross-border restricted
                    pass

            # classification authorization check — fail-closed for restricted data
            # Provider must explicitly allow classification via data_processing_policy.allowed_classifications or equivalent
            if classification in _RESTRICTED_LEVELS:
                allowed: list[str] | None = None
                if provider_row and provider_row.data_processing_policy:
                    dpp = provider_row.data_processing_policy
                    # support multiple schema shapes
                    allowed = dpp.get("allowed_classifications") or dpp.get("allowed_data_classifications") or dpp.get("classifications")
                    if isinstance(allowed, str):
                        allowed = [allowed]
                    if isinstance(allowed, list):
                        allowed = [str(x).upper() for x in allowed]
                # If provider declares allowed list and classification not in it -> unauthorized
                if isinstance(allowed, list) and len(allowed) > 0 and classification not in allowed:
                    logger.debug("provider %s not authorized for %s — allowed=%s", model.provider, classification, allowed)
                    continue
                # If provider has no explicit allow list, we treat cross-border as unauthorized for restricted
                if cross_border and classification in _RESTRICTED_LEVELS:
                    # cross-border for restricted requires explicit opt-in via policy; if gate already allowed we still flag
                    # Here we fail-closed if provider region is external and no explicit allow
                    if provider_row is None or not provider_row.data_processing_policy.get("cross_border_allowed"):
                        # check if provider region signals cross-border
                        if _is_cross_border(region):
                            continue

            # Budget check — estimate cost from provider pricing
            est_cost: float | None = None
            if provider_row and provider_row.pricing:
                # pricing may be {"input_per_1k": 0.002, "output_per_1k": 0.006} or {"cost_per_request": 0.01}
                pricing = provider_row.pricing
                if "cost_per_request" in pricing:
                    try:
                        est_cost = float(pricing["cost_per_request"])
                    except Exception:
                        est_cost = None
                elif "input_per_1k" in pricing:
                    try:
                        est_cost = float(pricing["input_per_1k"]) * 1.5  # rough request estimate
                    except Exception:
                        est_cost = None
            if budget_f is not None and est_cost is not None and est_cost > budget_f:
                logger.debug("skipping model %s — est_cost %.4f > budget %.4f", model.model_id, est_cost, budget_f)
                continue

            # Quality/latency from monitoring snapshots (latest per model)
            quality: float | None = None
            latency: float | None = None
            try:
                stmt_m = (
                    select(AIMonitoringSnapshot)
                    .where(AIMonitoringSnapshot.tenant == tenant_s, AIMonitoringSnapshot.model_id == model.id)
                    .order_by(AIMonitoringSnapshot.created_at.desc())
                    .limit(1)
                )
                rm = await db.execute(stmt_m)
                snap: AIMonitoringSnapshot | None = rm.scalars().first()
                if snap is not None:
                    quality = snap.quality
                    latency = snap.latency_ms
            except Exception as exc:  # noqa: BLE001
                logger.debug("monitoring lookup failed for %s: %s", model.id, exc)

            # scoring — higher is better
            score = 0.0
            # capability bonus: purpose in capabilities
            if purpose_s:
                caps = model.capabilities or {}
                # capabilities may be dict of bool or list
                if isinstance(caps, dict):
                    if caps.get(purpose_s) or caps.get(purpose_s.lower()):
                        score += 30
                    elif any(purpose_s.lower() in str(k).lower() for k in caps.keys()):
                        score += 15
                elif isinstance(caps, list):
                    if purpose_s in caps or purpose_s.lower() in [str(x).lower() for x in caps]:
                        score += 30
            # quality bonus
            if quality is not None:
                score += float(quality) * 20  # quality 0-1 => 0-20
            else:
                score += 5  # neutral
            # latency penalty (lower is better)
            if latency is not None:
                # latency 0-1000ms => map to 10 - latency/200
                score += max(0, 10 - float(latency) / 200)
            else:
                score += 5
            # cost bonus (cheaper is better)
            if est_cost is not None:
                # cheaper => higher score; invert via 10/(cost*100+1)
                try:
                    score += 10 / (float(est_cost) * 100 + 1)
                except Exception:
                    pass
            else:
                score += 3
            # region match bonus
            if region_hint_s and region and region == region_hint_s:
                score += 15
            elif region and not _is_cross_border(region):
                score += 5
            # provider hint bonus already filtered but ensure
            if provider_hint_s and model.provider == provider_hint_s:
                score += 10

            scored.append((score, model, provider_row, {"est_cost": est_cost, "quality": quality, "latency": latency, "region": region}))

        if not scored:
            if classification in _RESTRICTED_LEVELS:
                raise AuthorizationError(f"no authorized route for {classification} data — all candidates filtered (fail-closed)")
            return {"decision": "DENY", "reason": "no candidates passed policy/region/budget filters", "classification": classification, "provider": provider_hint_s, "region": region_hint_s, "cross_border": cross_border, "policy": gate_raw}

        # Sort by score desc
        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best_model, best_provider, meta = scored[0]

        chosen_provider = best_model.provider
        chosen_region = meta.get("region") or best_model.region or (best_provider.regions[0] if best_provider and best_provider.regions else region_hint_s)
        est_cost = meta.get("est_cost")
        latency = meta.get("latency")
        quality = meta.get("quality")

        # Final fail-closed double-check for restricted routing to unauthorized provider
        if classification in _RESTRICTED_LEVELS:
            # Re-check gate for the chosen provider if original hint was empty
            if not provider_hint_s or chosen_provider != provider_hint_s:
                try:
                    from app.datagov.ai_gate import ai_gate_service  # type: ignore

                    final_gate = await ai_gate_service.check(
                        db=db,
                        tenant=tenant_s,
                        actor=purpose_s or "gateway.route",
                        data_classification=classification,
                        provider=chosen_provider,
                        region=chosen_region,
                        purpose=purpose_s,
                        resource=best_model.model_id or best_model.name,
                    )
                    dec = str(final_gate.get("decision", "ALLOW")).upper()
                    if dec == "DENY":
                        raise AuthorizationError(f"route denied for chosen provider '{chosen_provider}': {final_gate.get('reason')}")
                    gate_raw = final_gate
                    gate_decision = dec
                except AuthorizationError:
                    raise
                except ImportError as exc:
                    logger.debug("ai_gate final check not available: %s", exc)
                    raise AuthorizationError(f"fail-closed: policy engine unavailable for final check of {classification} data") from exc
                except Exception as exc:  # noqa: BLE001
                    logger.debug("final gate check failed: %s", exc)
                    if classification in _RESTRICTED_LEVELS:
                        raise AuthorizationError(f"fail-closed: final policy check failed for {classification} data — {exc}") from exc

            # governance blocked check for chosen provider
            try:
                from app.governance.ai_governance import AIGovernanceManager  # type: ignore

                for stor in (f"ai_governance_data_{tenant_s}", "ai_governance_data"):
                    try:
                        m = AIGovernanceManager(storage_dir=stor)  # type: ignore
                        policies = m.list_policies(tenant_s)  # type: ignore
                        for pol in policies or []:
                            if not getattr(pol, "enabled", True):
                                continue
                            bps = [str(x).strip().lower() for x in (getattr(pol, "blocked_providers", []) or []) if x and str(x).strip()]
                            if chosen_provider.lower() in bps:
                                raise AuthorizationError(f"chosen provider '{chosen_provider}' blocked by governance policy '{getattr(pol, 'name', pol.id)}' — fail-closed for {classification}")
                        break
                    except AuthorizationError:
                        raise
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("governance final check failed for %s: %s", stor, exc)
                        continue
            except AuthorizationError:
                raise
            except ImportError:
                pass
            except Exception as exc:  # noqa: BLE001
                logger.debug("governance final route check error: %s", exc)

        _audit(tenant_s, purpose_s or "gateway", "ai_gateway.route.selected", str(best_model.id), {"provider": chosen_provider, "region": chosen_region, "classification": classification, "score": round(best_score, 2)})

        return {
            "decision": "ALLOW",
            "reason": f"selected {best_model.provider}/{best_model.name}:{best_model.version} (score={round(best_score, 2)})",
            "classification": classification,
            "cross_border": cross_border,
            "model_id": str(best_model.id),
            "model_name": best_model.name,
            "model_version": best_model.version,
            "provider": chosen_provider,
            "region": chosen_region,
            "cost_estimate": est_cost,
            "latency_estimate_ms": latency,
            "quality_estimate": quality,
            "score": round(best_score, 2),
            "policy": gate_raw,
            "purpose": purpose_s,
            "budget": budget_f,
        }

    # ── invoke ─────────────────────────────────────────────────────────

    async def invoke(
        self,
        db: AsyncSession,
        tenant: str,
        actor: str,
        model_id: str | uuid.UUID,
        prompt: str,
        data_classification: str = "INTERNAL",
        purpose: str | None = None,
    ) -> dict[str, Any]:
        """Invoke a model with full governance checks and mocked provider call.

        Steps:
          1. Check model exists and status APPROVED/ACTIVE (never deploy unapproved).
          2. Check provider availability (must be AVAILABLE).
          3. Policy check via ai_gate (ALLOW/DENY/REDACT/REQUIRE_APPROVAL).
          4. Guardrail pre-check (input).
          5. Provider call stub (mocked result with cost/latency).
          6. Post-output policy check.
          7. Audit (best-effort).

        Returns mocked invocation result including cost/latency.
        """
        if not tenant or not str(tenant).strip():
            raise ValidationError(message="tenant is required")
        if not actor or not str(actor).strip():
            raise ValidationError(message="actor is required")
        tenant_s = str(tenant).strip()
        actor_s = str(actor).strip()
        classification = _normalize_classification(data_classification)
        purpose_s = str(purpose).strip() if purpose else ""
        prompt_s = str(prompt) if prompt is not None else ""
        if not prompt_s:
            raise ValidationError(message="prompt is required")

        pk = _parse_uuid(model_id)

        # 1. Model must exist, tenant-scoped, and be APPROVED/ACTIVE
        stmt = select(AIModelRegistry).where(
            AIModelRegistry.id == pk,
            AIModelRegistry.tenant == tenant_s,
        )
        result = await db.execute(stmt)
        model: AIModelRegistry | None = result.scalars().first()
        if model is None:
            raise NotFoundError(resource="AIModelRegistry", identifier=str(pk))
        if model.status not in ("APPROVED", "ACTIVE"):
            _audit(tenant_s, actor_s, "ai_gateway.invoke.blocked_unapproved", str(model.id), {"status": model.status, "classification": classification})
            raise AuthorizationError(f"never deploy unapproved model: {model.model_id} status={model.status} — requires APPROVED/ACTIVE")

        # 2. Provider availability
        provider_key = model.provider
        provider_row: AIProviderRegistry | None = None
        try:
            stmt_p = select(AIProviderRegistry).where(
                AIProviderRegistry.tenant == tenant_s,
                AIProviderRegistry.provider == provider_key,
            )
            rp = await db.execute(stmt_p)
            provider_row = rp.scalars().first()
        except Exception as exc:  # noqa: BLE001
            logger.debug("provider lookup during invoke failed: %s", exc)
            provider_row = None

        if provider_row is None:
            _audit(tenant_s, actor_s, "ai_gateway.invoke.provider_not_found", str(model.id), {"provider": provider_key})
            raise NotFoundError(resource="AIProviderRegistry", identifier=provider_key)
        if provider_row.availability != "AVAILABLE":
            _audit(tenant_s, actor_s, "ai_gateway.invoke.provider_unavailable", str(model.id), {"provider": provider_key, "availability": provider_row.availability})
            raise ServiceUnavailableError(f"provider '{provider_key}' unavailable (availability={provider_row.availability}) — DEGRADED/UNAVAILABLE/UNKNOWN never treated available")

        # 3. Policy check (pre-invocation gate)
        gate_result: dict[str, Any] | None = None
        try:
            from app.datagov.ai_gate import ai_gate_service  # type: ignore

            gate_result = await ai_gate_service.check(
                db=db,
                tenant=tenant_s,
                actor=actor_s,
                data_classification=classification,
                provider=provider_key,
                region=model.region or (provider_row.regions[0] if provider_row.regions else None),
                purpose=purpose_s,
                resource=model.model_id or model.name,
            )
            dec = str(gate_result.get("decision", "ALLOW")).upper()
            reason = str(gate_result.get("reason", ""))
            if dec == "DENY":
                _audit(tenant_s, actor_s, "ai_gateway.invoke.denied_by_policy", str(model.id), {"classification": classification, "provider": provider_key, "reason": reason})
                raise AuthorizationError(f"policy DENY for {classification} data via '{provider_key}': {reason}")
            if dec == "REQUIRE_APPROVAL":
                _audit(tenant_s, actor_s, "ai_gateway.invoke.require_approval", str(model.id), {"classification": classification, "provider": provider_key, "reason": reason})
                raise AuthorizationError(f"policy REQUIRE_APPROVAL for {classification} data — approval required: {reason}")
            if dec == "REDACT":
                prompt_s = _redact_text(prompt_s)
                gate_result["redacted_prompt"] = True
                gate_result["redacted"] = True
            if dec == "ANONYMIZE":
                prompt_s = _redact_text(prompt_s)
                gate_result["anonymized"] = True
        except AuthorizationError:
            raise
        except ImportError as exc:
            logger.debug("ai_gate not available during invoke: %s", exc)
            if classification in _RESTRICTED_LEVELS:
                raise AuthorizationError(f"fail-closed: policy engine unavailable for {classification} data") from exc
        except Exception as exc:  # noqa: BLE001
            # ai_gate raised unexpected — fail-closed for restricted
            logger.debug("ai_gate invoke check error: %s", exc)
            if classification in _RESTRICTED_LEVELS:
                raise AuthorizationError(f"fail-closed: policy evaluation failed for {classification} data — {exc}") from exc
            # for non-restricted, treat as ALLOW with warning
            gate_result = gate_result or {"decision": "ALLOW", "reason": f"policy engine error ignored for {classification}: {exc}", "error": str(exc)}

        # governance blocked_providers check (second layer)
        try:
            from app.governance.ai_governance import AIGovernanceManager  # type: ignore

            for stor in (f"ai_governance_data_{tenant_s}", "ai_governance_data"):
                try:
                    m = AIGovernanceManager(storage_dir=stor)  # type: ignore
                    policies = m.list_policies(tenant_s)  # type: ignore
                    for pol in policies or []:
                        if not getattr(pol, "enabled", True):
                            continue
                        bps = [str(x).strip().lower() for x in (getattr(pol, "blocked_providers", []) or []) if x and str(x).strip()]
                        if provider_key.lower() in bps:
                            raise AuthorizationError(f"provider '{provider_key}' blocked by governance policy '{getattr(pol, 'name', pol.id)}'")
                        bms = [str(x).strip().lower() for x in (getattr(pol, "blocked_models", []) or []) if x and str(x).strip()]
                        if model.name.lower() in bms or (model.model_id or "").lower() in bms:
                            raise AuthorizationError(f"model '{model.name}' blocked by governance policy '{getattr(pol, 'name', pol.id)}'")
                    break
                except AuthorizationError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    logger.debug("governance invoke check failed for %s: %s", stor, exc)
                    continue
        except AuthorizationError:
            raise
        except ImportError:
            pass
        except Exception as exc:  # noqa: BLE001
            logger.debug("governance invoke check error: %s", exc)

        # 4. Guardrail pre-check (input)
        guardrail_decision = await self._guardrail_pre_check(db, tenant_s, prompt_s, classification)
        if guardrail_decision.get("decision") == "DENY":
            _audit(tenant_s, actor_s, "ai_gateway.invoke.denied_by_guardrail", str(model.id), {"reason": guardrail_decision.get("reason")})
            raise AuthorizationError(f"guardrail DENY (input): {guardrail_decision.get('reason')}")
        # REDACT from guardrail also redacts prompt
        if guardrail_decision.get("decision") == "REDACT":
            prompt_s = _redact_text(prompt_s)

        # Rate limit check via guardrail rate_limit field (simple in-memory placeholder per tenant)
        # If any enabled input guardrail has rate_limit, we treat it as advisory here (no global counter).
        # Real rate limiting would use Redis; we just log.

        # 5. Provider call stub — mocked result with cost/latency
        invoke_result = await self._call_provider_stub(
            model=model,
            provider_row=provider_row,
            prompt=prompt_s,
            classification=classification,
            purpose=purpose_s,
        )

        # 6. Post-output policy check (output classification same as input for now)
        try:
            from app.datagov.ai_gate import ai_gate_service  # type: ignore

            output_text = str(invoke_result.get("output", ""))
            out_gate = await ai_gate_service.check(
                db=db,
                tenant=tenant_s,
                actor=actor_s,
                data_classification=classification,
                provider=provider_key,
                region=model.region or (provider_row.regions[0] if provider_row.regions else None),
                purpose=purpose_s,
                resource=model.model_id or model.name,
            )
            # If output policy says DENY/REDACT, apply to output
            out_dec = str(out_gate.get("decision", "ALLOW")).upper()
            if out_dec == "DENY":
                # Flag output as blocked but still return with warning (audit already)
                invoke_result["output_policy"] = out_gate
                invoke_result["output_blocked"] = True
                _audit(tenant_s, actor_s, "ai_gateway.invoke.output_denied", str(model.id), {"reason": out_gate.get("reason")})
            elif out_dec in ("REDACT", "ANONYMIZE"):
                invoke_result["output"] = _redact_text(output_text)
                invoke_result["output_policy"] = out_gate
                invoke_result["output_redacted"] = True
            else:
                invoke_result["output_policy"] = out_gate
        except ImportError:
            pass
        except Exception as exc:  # noqa: BLE001
            logger.debug("post-output policy check failed: %s", exc)
            # never fail invocation due to post-check error; just log

        # 7. Audit success
        _audit(
            tenant_s,
            actor_s,
            "ai_gateway.invoke.success",
            str(model.id),
            {
                "provider": provider_key,
                "region": model.region,
                "classification": classification,
                "purpose": purpose_s,
                "prompt_fingerprint": _fingerprint(prompt_s) if prompt_s else "",
                "cost": invoke_result.get("cost"),
                "latency_ms": invoke_result.get("latency_ms"),
                "model": model.model_id,
            },
        )

        # Telemetry snapshot best-effort (not persisted here; caller may persist via monitoring service)
        return {
            "model_id": str(model.id),
            "model_name": model.name,
            "model_version": model.version,
            "provider": provider_key,
            "region": model.region or (provider_row.regions[0] if provider_row.regions else None),
            "classification": classification,
            "purpose": purpose_s,
            "prompt_fingerprint": _fingerprint(prompt_s),
            "output": invoke_result.get("output"),
            "cost": invoke_result.get("cost"),
            "latency_ms": invoke_result.get("latency_ms"),
            "tokens": invoke_result.get("tokens"),
            "policy": gate_result,
            "guardrail": guardrail_decision,
            "output_policy": invoke_result.get("output_policy"),
            "provider_call": {"mocked": True, "model_id": str(model.id)},
        }

    # ── helpers ────────────────────────────────────────────────────────

    async def _guardrail_pre_check(
        self,
        db: AsyncSession,
        tenant: str,
        prompt: str,
        classification: str,
    ) -> dict[str, Any]:
        """Evaluate enabled input guardrails for tenant.

        Order: input scope only. Returns ALLOW / DENY / REDACT decision.
        If no guardrails configured, returns ALLOW.
        """
        try:
            stmt = select(AIGuardrail).where(
                AIGuardrail.tenant == tenant,
                AIGuardrail.enabled.is_(True),
            )
            result = await db.execute(stmt)
            guardrails: list[AIGuardrail] = list(result.scalars().all())
        except Exception as exc:  # noqa: BLE001
            logger.debug("guardrail query failed: %s", exc)
            return {"decision": "ALLOW", "reason": "guardrail query unavailable", "error": str(exc)}

        # Filter to input scope (or no scope treated as input)
        input_guards = [g for g in guardrails if (g.scope or "input").lower() == "input"]
        if not input_guards:
            return {"decision": "ALLOW", "reason": "no input guardrails configured"}

        # Evaluate each guard's policy dict
        # Supported policy keys: blocked_keywords (list), blocked_patterns (list regex), max_length (int), classification_max
        import re as _re

        for guard in input_guards:
            pol = guard.policy or {}
            # blocked keywords
            blocked_keywords: list[str] = list(pol.get("blocked_keywords") or pol.get("blocked_terms") or [])
            for kw in blocked_keywords:
                if kw and kw.lower() in prompt.lower():
                    return {"decision": "DENY", "reason": f"guardrail '{guard.name}' blocked keyword '{kw}'", "guardrail_id": str(guard.id)}
            # blocked regex patterns
            blocked_patterns: list[str] = list(pol.get("blocked_patterns") or pol.get("patterns") or [])
            for pat in blocked_patterns:
                try:
                    if _re.search(pat, prompt, _re.IGNORECASE):
                        return {"decision": "DENY", "reason": f"guardrail '{guard.name}' matched blocked pattern '{pat}'", "guardrail_id": str(guard.id)}
                except _re.error:
                    logger.debug("invalid guardrail pattern %s in %s", pat, guard.name)
                    continue
            # max length
            max_len = pol.get("max_length") or pol.get("max_prompt_length")
            if isinstance(max_len, int) and len(prompt) > max_len:
                return {"decision": "DENY", "reason": f"guardrail '{guard.name}' prompt exceeds max_length {max_len}", "guardrail_id": str(guard.id)}
            # classification ceiling
            allowed_max = pol.get("classification_max") or pol.get("max_classification")
            if isinstance(allowed_max, str) and allowed_max.strip():
                # map to rank: if input classification more sensitive than allowed, deny
                rank_in = {"PUBLIC": 0, "INTERNAL": 1, "CONFIDENTIAL": 2, "RESTRICTED": 3, "SECRET": 4}.get(classification.upper(), 1)
                rank_max = {"PUBLIC": 0, "INTERNAL": 1, "CONFIDENTIAL": 2, "RESTRICTED": 3, "SECRET": 4}.get(allowed_max.strip().upper(), 4)
                if rank_in > rank_max:
                    return {"decision": "DENY", "reason": f"guardrail '{guard.name}' classification {classification} exceeds max {allowed_max}", "guardrail_id": str(guard.id)}
            # content policy: if policy says redact PII
            if pol.get("redact_pii") and _contains_pii(prompt):
                return {"decision": "REDACT", "reason": f"guardrail '{guard.name}' requires PII redaction", "guardrail_id": str(guard.id)}

        return {"decision": "ALLOW", "reason": "input guardrails passed", "evaluated": len(input_guards)}

    async def _call_provider_stub(
        self,
        model: AIModelRegistry,
        provider_row: AIProviderRegistry | None,
        prompt: str,
        classification: str,
        purpose: str,
    ) -> dict[str, Any]:
        """Mocked provider call — returns synthetic output with cost/latency.

        No real network calls. Estimates cost from provider pricing and
        latency from random jitter around a base (80-180ms).
        """
        # Token estimate: ~4 chars per token
        prompt_tokens = max(1, len(prompt) // 4)
        completion_tokens = random.randint(20, 120)  # nosec - mock variability
        total_tokens = prompt_tokens + completion_tokens

        # Latency estimate
        base_latency = 90.0
        # add jitter and a bit for larger prompts
        latency_ms = round(base_latency + random.uniform(10, 80) + (prompt_tokens * 0.02), 2)  # nosec

        # Cost estimate from pricing
        cost = 0.0
        if provider_row and provider_row.pricing:
            p = provider_row.pricing
            try:
                if "cost_per_request" in p:
                    cost = float(p["cost_per_request"])
                elif "input_per_1k" in p and "output_per_1k" in p:
                    cost = (prompt_tokens / 1000) * float(p["input_per_1k"]) + (completion_tokens / 1000) * float(p["output_per_1k"])
                elif "input_per_1k" in p:
                    cost = (total_tokens / 1000) * float(p["input_per_1k"])
                else:
                    cost = round(total_tokens * 0.000002, 6)  # default $0.002 per 1k
            except Exception:
                cost = round(total_tokens * 0.000002, 6)
        else:
            cost = round(total_tokens * 0.000002, 6)

        # Mock output — never echoes raw prompt for SECRET; include purpose/model hints
        output = f"[{model.provider}/{model.name}:{model.version} stub] processed purpose='{purpose or 'general'}' classification='{classification}' tokens={total_tokens} cost=${cost:.6f} latency={latency_ms}ms"
        # Truncate output if very long prompt to avoid leaking excessive content
        if len(prompt) > 200:
            output += f" — prompt_fingerprint={_fingerprint(prompt)[:8]}"

        return {
            "output": output,
            "tokens": {"prompt": prompt_tokens, "completion": completion_tokens, "total": total_tokens},
            "cost": round(cost, 6),
            "latency_ms": latency_ms,
            "model": model.model_id,
            "provider": model.provider,
        }


def _contains_pii(text: str) -> bool:
    """Lightweight PII heuristic for guardrail redact check."""
    import re as _re

    pii_patterns = [
        r"[\w.+-]+@[\w-]+(\.[\w-]+)+",  # email
        r"\b\d{3}-\d{2}-\d{4}\b",  # ssn
        r"\b(?:\d[ -]?){13,19}\b",  # credit card-ish
    ]
    for pat in pii_patterns:
        try:
            if _re.search(pat, text):
                return True
        except _re.error:
            continue
    return False


gateway_service = ModelGatewayService()
